"""Citation grounding: preparation, noise suppression, and reporting.

The verification itself is ndlaw's ``check_draft`` — it carries jetcite for
extraction and the ND corpus for lookup, so re-implementing either here would
duplicate maintained work with worse coverage.  An earlier version of this
module did exactly that and missed findings ``check_draft`` catches, including
a parallel reporter cite that resolves to no ND opinion.

What remains here is the work ``check_draft`` cannot do, because it does not
know it is reading a PDF extraction of an appellate brief:

* **Pre-cleaning.**  Extraction interleaves page numbers into the middle of
  quotations.  Sent as-is, a correctly quoted brief comes back flagged as a
  misquotation over a stray "8".
* **Noise suppression.**  ndlaw's canonical captions carry database
  annotations — "(Confidential)", "(cross-reference w/20990001)" — that are
  not part of the case name.  Compared literally, "Lucas v. Lucas" scores
  0.491 against "Lucas v. Lucas (cross-reference w/20990001)", and a correct
  citation is reported as name drift.
* **Locating findings in the brief** by paragraph number rather than by a
  window of raw text.
* **Keeping the whole thing advisory** — see ``CitationReview``.

Scope is existence, case-name identity, and quotation accuracy.  Whether an
authority supports the proposition it is cited for is not assessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- Preparing the text ------------------------------------------------------

# A page number lands mid-sentence in extracted text: "...clear understanding
# of \n\n8 \n\nits decision."  Left in, it breaks an otherwise verbatim
# quotation and produces a misquotation flag against a sound brief.
_INTERLEAVED_PAGE_NUM_RE = re.compile(r"\n[ \t]*\d{1,3}[ \t]*\n")

# Brief paragraph markers, in the forms real briefs use.
_BRIEF_PARA_RE = re.compile(
    r"(?:^|\n)\s*(?:\[\s*¶?\s*(\d{1,4})\s*\]|¶+\s*(\d{1,4}))")


def clean_draft_text(text: str) -> str:
    """Prepare extracted brief text for ``check_draft``.

    Removes the page numbers extraction leaves on their own line, which would
    otherwise turn up inside quotations.  Paragraph markers are kept: they are
    how a finding is located in the brief.
    """
    if not text:
        return ""
    # Twice, so two page breaks falling close together both go.
    cleaned = _INTERLEAVED_PAGE_NUM_RE.sub("\n", text)
    return _INTERLEAVED_PAGE_NUM_RE.sub("\n", cleaned)


def paragraph_for_context(text: str, context: str) -> Optional[int]:
    """The brief paragraph a flag's context sits in, if it can be located.

    ``check_draft`` reports where a flag came from as a window of raw text.
    A clerk needs a paragraph number, so the window is located in the brief
    and the nearest preceding marker returned.
    """
    if not text or not context:
        return None
    head = " ".join(context.split())[:60].split()[:6]
    if not head:
        return None
    m = re.search(r"\s+".join(re.escape(w) for w in head), text)
    if m is None:
        return None
    last = None
    for mark in _BRIEF_PARA_RE.finditer(text):
        if mark.start() > m.start():
            break
        last = mark.group(1) or mark.group(2)
    return int(last) if last else None


# --- Noise suppression -------------------------------------------------------

# Below this similarity, a name difference is worth raising.  Applied only
# after the canonical caption's bookkeeping is stripped: "Lucas v. Lucas"
# scores 0.491 against "Lucas v. Lucas (cross-reference w/20990001)" and is a
# correct citation, so comparing raw captions would flag good work.
NAME_SIMILARITY_FLOOR = 0.6

# Parentheticals ndlaw appends to a caption for its own bookkeeping.  They are
# not part of the case name and must not count against it.
_CAPTION_ANNOTATION_RE = re.compile(
    r"\s*\((?:confidential|cross-reference[^)]*|consolidated[^)]*|"
    r"per\s+curiam|corrected[^)]*|amended[^)]*|on\s+rehearing[^)]*)\)",
    re.IGNORECASE,
)

# Party words that carry no identifying force when comparing captions.
_CAPTION_FILLER_RE = re.compile(
    r"\b(?:et\s+al\.?|and\s+others|inc\.?|llc|l\.l\.c\.|co\.?|corp\.?)\b",
    re.IGNORECASE,
)


def normalize_caption(name: str) -> str:
    """Strip bookkeeping from a case caption so two forms can be compared."""
    if not name:
        return ""
    out = _CAPTION_ANNOTATION_RE.sub("", name)
    out = _CAPTION_FILLER_RE.sub("", out)
    out = re.sub(r"[.,]", " ", out)
    return " ".join(out.split()).lower()


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def name_drift_is_real(written: str, canonical: str) -> bool:
    """True when two captions differ by more than style or bookkeeping.

    ndlaw reports drift against its raw caption.  A brief writing the fuller
    "Davis o/b/o HJR & CER v. Romanyshyn" for "Davis, et al. v. Romanyshyn",
    or the plain "Lucas v. Lucas" for a caption carrying a cross-reference
    note, is citing correctly.  Only a genuine mismatch should reach a reader.
    """
    left, right = normalize_caption(written), normalize_caption(canonical)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return False
    return _similarity(left, right) < NAME_SIMILARITY_FLOOR


# --- Findings ----------------------------------------------------------------

# check_draft flag types this pass reports.  Treatment (S3) and currency (S4)
# are not requested, and proposition support is out of scope.
FLAG_MISQUOTATION = "misquotation"
FLAG_UNRESOLVED = "unresolved_case_cite"
FLAG_NAME_DRIFT = "case_name_drift"

_REPORTABLE = {FLAG_MISQUOTATION, FLAG_UNRESOLVED, FLAG_NAME_DRIFT}


@dataclass
class CitationFinding:
    """One citation worth a reader's attention."""

    kind: str
    severity: str = ""
    message: str = ""
    cited_as: str = ""
    written_name: str = ""
    canonical_name: str = ""
    quote: str = ""
    closest_text: str = ""
    differences: list[str] = field(default_factory=list)
    context: str = ""
    brief_paragraph: Optional[int] = None

    @property
    def headline(self) -> str:
        if self.kind == FLAG_UNRESOLVED:
            return f"{self.cited_as} does not resolve to any ND authority"
        if self.kind == FLAG_NAME_DRIFT:
            return (f"brief names it {self.written_name}; "
                    f"the reporter shows {self.canonical_name}")
        if self.kind == FLAG_MISQUOTATION:
            return "quotation does not match the authority's text"
        return self.kind.replace("_", " ")


@dataclass
class CitationReview:
    """The citation-grounding pass as a whole.

    Advisory throughout.  Rule compliance is governed by the appellate rules;
    whether a brief's authorities are accurately cited is a different
    question, and it must not move the Accept / Correction Letter / Reject
    recommendation.  Nothing here is a CheckResult, for that reason.
    """

    ndlaw_available: bool = True
    coverage_line: str = ""
    findings: list[CitationFinding] = field(default_factory=list)
    suppressed: int = 0
    unavailable_reason: str = ""

    @property
    def flagged(self) -> list[CitationFinding]:
        return self.findings

    @classmethod
    def unavailable(cls, reason: str = "") -> "CitationReview":
        """No lookups were possible — say so rather than omitting the section."""
        return cls(
            ndlaw_available=False,
            coverage_line=(
                "No citation was verified: the ndlaw research tools were not "
                "available in this session. Citations in this brief are "
                "unverified, not confirmed."
            ),
            unavailable_reason=reason,
        )

    @classmethod
    def from_check_draft(cls, payload: dict, brief_text: str = "") -> "CitationReview":
        """Build a review from ndlaw ``check_draft`` output.

        Name-drift flags whose captions differ only by ndlaw's own
        bookkeeping are dropped and counted, not shown: reporting them would
        put a false flag on a correctly cited case in nearly every brief.
        """
        summary = payload.get("summary") or {}
        findings: list[CitationFinding] = []
        suppressed = 0

        for flag in payload.get("flags") or []:
            kind = flag.get("type", "")
            if kind not in _REPORTABLE:
                continue
            if kind == FLAG_NAME_DRIFT and not name_drift_is_real(
                flag.get("written_name", ""), flag.get("canonical_name", "")
            ):
                suppressed += 1
                continue
            cited = flag.get("cited_as", "")
            if isinstance(cited, list):
                cited = ", ".join(cited)
            context = flag.get("draft_context", "")
            findings.append(CitationFinding(
                kind=kind,
                severity=flag.get("severity", ""),
                message=flag.get("message", ""),
                cited_as=cited,
                written_name=flag.get("written_name", ""),
                canonical_name=flag.get("canonical_name", ""),
                quote=flag.get("quote", ""),
                closest_text=flag.get("closest_text", ""),
                differences=list(flag.get("differences") or []),
                context=context,
                brief_paragraph=paragraph_for_context(brief_text, context),
            ))

        return cls(
            ndlaw_available=True,
            coverage_line=_coverage_line(summary, payload, suppressed),
            findings=findings,
            suppressed=suppressed,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "CitationReview":
        """Read a stored review, or a raw ``check_draft`` payload."""
        if not d.get("ndlaw_available", True):
            review = cls.unavailable(d.get("unavailable_reason", ""))
            if d.get("coverage_line"):
                review.coverage_line = d["coverage_line"]
            return review
        if "summary" in d or "flags" in d:
            return cls.from_check_draft(d, d.get("brief_text", ""))
        return cls(
            ndlaw_available=True,
            coverage_line=d.get("coverage_line", ""),
            findings=[CitationFinding(**f) for f in d.get("findings", [])],
            suppressed=d.get("suppressed", 0),
        )


def _coverage_line(summary: dict, payload: dict, suppressed: int) -> str:
    """State what was checked before stating what was found."""
    cases = summary.get("case_citations", 0)
    resolved = summary.get("cases_resolved", 0)
    quotes = summary.get("quotations", 0)
    checked = summary.get("quotations_checked", 0)
    authorities = summary.get("authority_citations", 0)

    parts = [f"{cases} case citation(s) found, {resolved} resolved against the "
             f"ND corpus"]
    if authorities:
        parts.append(f"{authorities} statute/rule citation(s) checked")
    if quotes:
        parts.append(f"{checked} of {quotes} attributed quotation(s) verified")
    if suppressed:
        parts.append(
            f"{suppressed} case-name difference(s) set aside as the reporter's "
            f"own annotation rather than a discrepancy")

    unchecked = payload.get("unchecked") or {}
    if unchecked:
        total = sum(len(v) if isinstance(v, list) else 1 for v in unchecked.values())
        parts.append(f"{total} citation(s) outside the ND corpus and not checked")
    else:
        parts.append("authority outside North Dakota is not checked")

    return ("; ".join(parts) + ". Whether an authority supports the proposition "
            "it is cited for was not assessed. Unchecked citations are "
            "unverified, not confirmed.")
