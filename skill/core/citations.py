"""Citation extraction and scoping for the citation-grounding pass.

This module is deterministic and dependency-free: it finds citations in a
brief, works out which ones can be verified and which cannot, and decides
what is worth looking up.  It performs no lookups itself.  Retrieval runs
one level up, where ndlaw is reachable (see SKILL.md, Phase 2C), and the
results come back as JSON.

Scope follows from what can actually be checked.  ndlaw covers North
Dakota, so ND authorities can be verified against their text; a federal or
sister-state citation can be *found* here but not confirmed, and it is
reported as unchecked rather than quietly counted as sound.

Why not jetcite: it parses more jurisdictions and carries the antecedent
case name, but it needs beautifulsoup4, httpx, markdownify and pdfplumber
at import time, and the deployed skill installs PyMuPDF alone.  Extraction
sits behind ``extract_citations`` so jetcite can replace it later without
disturbing anything downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- Citation kinds ---------------------------------------------------------

ND_CASE = "nd_case"            # 2024 ND 88 — medium-neutral, verifiable
ND_STATUTE = "nd_statute"      # N.D.C.C. § 14-09-06.2
ND_RULE = "nd_rule"            # N.D.R.App.P. 32(a)(5)
REGIONAL = "regional"          # 1002 N.W.2d 44 — usually parallel to an ND cite
FOREIGN = "foreign"            # 501 U.S. 200, 123 F.3d 456 — outside ndlaw

VERIFIABLE_KINDS = {ND_CASE, ND_STATUTE, ND_RULE}


@dataclass
class Citation:
    """One citation found in a brief."""

    raw: str
    kind: str
    start: int
    end: int
    normalized: str = ""
    antecedent_name: Optional[str] = None   # "Torgerson v. Bexley"
    pinpoint: Optional[str] = None          # "9", "9-11", "(1)(d)"
    proposition: str = ""                   # the sentence the cite supports
    quotation: Optional[str] = None         # quoted matter attributed to it
    paragraph: Optional[int] = None         # brief paragraph number, if numbered
    parallel_cite: Optional[str] = None     # e.g. the N.W.2d cite beside an ND cite

    @property
    def verifiable(self) -> bool:
        """True when ndlaw can be expected to reach this authority."""
        return self.kind in VERIFIABLE_KINDS

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "kind": self.kind,
            "normalized": self.normalized or self.raw,
            "antecedent_name": self.antecedent_name,
            "pinpoint": self.pinpoint,
            "proposition": self.proposition,
            "quotation": self.quotation,
            "paragraph": self.paragraph,
            "parallel_cite": self.parallel_cite,
            "verifiable": self.verifiable,
        }


# --- Patterns ---------------------------------------------------------------

# "2024 ND 88", "2019 ND App 12" — the medium-neutral form Rule 11.6 requires
# "2024 ND 88" (Supreme Court) and "2019 ND App 12" (Court of Appeals) are
# different courts; the "App" must survive normalization or a lookup goes
# to the wrong case.
_ND_CASE_RE = re.compile(
    r"\b(?P<year>(?:18|19|20)\d{2})\s+ND(?P<app>\s+App)?\s+(?P<num>\d{1,4})\b")

# "N.D.C.C. § 14-09-06.2(1)(d)" — section symbol optional, spacing loose
_ND_STATUTE_RE = re.compile(
    r"\bN\.?\s?D\.?\s?C\.?\s?C\.?\s*"
    r"(?:§+|sec(?:tion)?s?\.?)?\s*"
    r"(?P<num>\d+(?:\.\d+)?-\d+(?:\.\d+)?-\d+(?:\.\d+)?)"
    r"(?P<sub>(?:\([^)\s]{1,6}\))*)",
    re.IGNORECASE,
)

# "N.D.R.App.P. 32(a)(5)", "N.D.R.Ct. 3.4(b)"
_ND_RULE_RE = re.compile(
    r"\bN\.?\s?D\.?\s?R\.?\s?(?P<set>App\.?\s?P|Ct|Civ\.?\s?P|Crim\.?\s?P|Ev)\.?\s*"
    r"(?P<num>\d+(?:\.\d+)?)"
    r"(?P<sub>(?:\([^)\s]{1,6}\))*)",
    re.IGNORECASE,
)

# "1002 N.W.2d 44" — the regional reporter, normally parallel to an ND cite
_REGIONAL_RE = re.compile(r"\b(?P<vol>\d{1,4})\s+N\.?\s?W\.?\s?(?:2d|3d)?\s+(?P<page>\d{1,4})\b")

# Federal and sister-state reporters — findable, not verifiable through ndlaw
_FOREIGN_RE = re.compile(
    r"\b\d{1,4}\s+(?:U\.?\s?S\.?|S\.?\s?Ct\.?|L\.?\s?Ed\.?(?:\s?2d)?|"
    r"F\.?\s?(?:2d|3d|4th|Supp\.?(?:\s?2d|\s?3d)?)?|"
    r"P\.?\s?(?:2d|3d)|A\.?\s?(?:2d|3d)|S\.?\s?E\.?\s?2d|S\.?\s?W\.?\s?(?:2d|3d)|"
    r"N\.?\s?E\.?\s?(?:2d|3d))\s+\d{1,4}\b"
)

# Pinpoint following a cite: ", ¶ 9", ", ¶¶ 9-11", ", para. 9", ", at ¶ 9"
_PINPOINT_RE = re.compile(
    r"^[\s,]*(?:at\s+)?(?:¶{1,2}|paras?\.?|paragraphs?)\s*"
    r"(?P<pin>\d{1,4}(?:\s*[-–]\s*\d{1,4})?)",
    re.IGNORECASE,
)

# "Torgerson v. Bexley" immediately preceding a cite
_CASE_NAME_RE = re.compile(
    r"(?P<name>(?:[A-Z][\w.'’-]*\s+)*[A-Z][\w.'’-]*"
    r"\s+v\.?\s+"
    r"(?:[A-Z][\w.'’-]*\s*)+?)"
    r"[\s,]*$"
)

# A quotation of at least a few words, straight or curly
_QUOTE_RE = re.compile(r"[\"“]([^\"”]{12,600})[\"”]")

# Brief paragraph markers: "[12]" or "¶ 12" at the start of a paragraph
_BRIEF_PARA_RE = re.compile(r"(?:^|\n)\s*(?:\[(\d{1,4})\]|¶\s*(\d{1,4}))")

# Abbreviations that take a period mid-sentence.  Splitting naively on ". "
# turns "Torgerson v. Bexley" into two sentences and truncates the
# proposition to a fragment.  Python's re has no variable-width lookbehind,
# so candidate split points are filtered in code instead.
_ABBREVIATIONS = {
    "v", "vs", "no", "nos", "inc", "co", "corp", "ltd", "assn", "dept", "div",
    "ed", "eds", "cf", "id", "supra", "app", "ct", "cts", "st", "stat", "sec",
    "secs", "ch", "art", "para", "paras", "pp", "p", "n", "nn", "jr", "sr",
    "mr", "mrs", "ms", "dr", "hon", "u", "s", "f", "a", "d", "w", "e", "c",
    "r", "ev", "civ", "crim", "n.w", "n.d", "u.s",
}

_SPLIT_CANDIDATE_RE = re.compile(r"[.!?]\s+(?=[A-Z\"“(\[])")
_LAST_WORD_RE = re.compile(r"([A-Za-z.]+)\.$")


def _split_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) spans of sentences, tolerant of legal abbreviations."""
    spans, start = [], 0
    for m in _SPLIT_CANDIDATE_RE.finditer(text):
        head = text[start:m.start() + 1]
        word = _LAST_WORD_RE.search(head.strip())
        if word and word.group(1).rstrip(".").lower() in _ABBREVIATIONS:
            continue          # an abbreviation, not a sentence end
        spans.append((start, m.start() + 1))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _paragraph_index(text: str) -> list[tuple[int, int]]:
    """(offset, paragraph number) for each numbered paragraph marker."""
    marks = []
    for m in _BRIEF_PARA_RE.finditer(text):
        num = m.group(1) or m.group(2)
        if num:
            marks.append((m.start(), int(num)))
    return marks


def _paragraph_for(offset: int, marks: list[tuple[int, int]]) -> Optional[int]:
    found = None
    for pos, num in marks:
        if pos <= offset:
            found = num
        else:
            break
    return found


# Introductory signals that carry no proposition of their own.
_SIGNAL_RE = re.compile(
    r"\b(?:see(?:\s+also|\s+generally)?|accord|cf|but\s+see|e\.?g\.?|"
    r"citing|quoting|contra|compare|internal\s+citations?\s+omitted)\b\.?",
    re.IGNORECASE,
)


def _is_citation_sentence(sentence: str, cite_raw: str) -> bool:
    """True when a sentence is citation and signal only.

    A citation sentence supports the sentence before it, so the proposition
    to test is that earlier sentence — not "Torgerson v. Bexley, 2024 ND 88,
    ¶ 9, 1002 N.W.2d 44.", which asserts nothing.
    """
    residue = sentence.replace(cite_raw, " ")
    residue = _SIGNAL_RE.sub(" ", residue)
    # Strip case names, reporter noise, pinpoints and punctuation
    residue = re.sub(r"[A-Z][\w.'’-]*\s+v\.?\s+[A-Z][\w.'’-]*", " ", residue)
    residue = re.sub(r"\d+\s+N\.?\s?W\.?\s?(?:2d|3d)?\s+\d+", " ", residue)
    residue = re.sub(r"¶{1,2}\s*[\d\s,–-]+", " ", residue)
    residue = re.sub(r"\(\d{4}\)", " ", residue)
    residue = re.sub(r"[^A-Za-z ]", " ", residue)
    return len(_normalize_space(residue)) < 25


def _sentence_around(text: str, start: int, end: int, cite_raw: str = "") -> str:
    """The proposition a citation is offered for.

    Normally the sentence containing the citation.  When that sentence is
    nothing but citation and signal, the proposition is the sentence before
    it, per ordinary citation practice.
    """
    para_start, para_end = _paragraph_bounds(text, start)
    window = text[para_start:para_end]
    rel = start - para_start
    spans = _split_sentences(window)

    for i, (s, e) in enumerate(spans):
        if s <= rel < e:
            sentence = _normalize_space(window[s:e])
            if cite_raw and _is_citation_sentence(sentence, cite_raw) and i > 0:
                prev = _normalize_space(window[spans[i - 1][0]:spans[i - 1][1]])
                prev = re.sub(r"^\[\d+\]\s*", "", prev)
                if prev:
                    return prev
            return re.sub(r"^\[\d+\]\s*", "", sentence)
    return _normalize_space(window[:400])


def _paragraph_bounds(text: str, offset: int) -> tuple[int, int]:
    """Start and end of the block of text containing *offset*.

    A citation can only be answerable for matter in its own paragraph.  An
    unbounded lookback attributed one paragraph's quotation to every
    citation in the brief.
    """
    starts = [m.start() for m in _BRIEF_PARA_RE.finditer(text)]
    para_start = max((s for s in starts if s <= offset), default=None)
    para_end = min((s for s in starts if s > offset), default=len(text))
    if para_start is None:
        blank = text.rfind("\n\n", 0, offset)
        para_start = blank + 2 if blank != -1 else 0
    return para_start, para_end


def _quotation_near(text: str, start: int, end: int) -> Optional[str]:
    """Quoted matter attributable to a citation.

    A brief may quote before citing ("...," the court held, Smith, 2020 ND 1)
    or after (Smith, 2020 ND 1 ("the text")).  Both are searched, but only
    within the citation's own paragraph: quoted matter three paragraphs
    away is somebody else's.
    """
    para_start, para_end = _paragraph_bounds(text, start)
    before = text[max(para_start, start - 700):start]
    quotes = _QUOTE_RE.findall(before)
    if quotes:
        return _normalize_space(quotes[-1])
    after = text[end:min(para_end, end + 300)]
    quotes = _QUOTE_RE.findall(after)
    if quotes:
        return _normalize_space(quotes[0])
    return None


def _antecedent_name(text: str, start: int) -> Optional[str]:
    """The case name immediately before a citation, if any."""
    window = text[max(0, start - 120):start]
    m = _CASE_NAME_RE.search(_normalize_space(window))
    if not m:
        return None
    name = _normalize_space(m.group("name"))
    # Guard against swallowing a lead-in verb or signal
    name = re.sub(r"^(?:see|accord|cf|e\.?g\.?|but see|citing|quoting|in)\s+", "",
                  name, flags=re.IGNORECASE)
    return name or None


def extract_citations(text: str) -> list[Citation]:
    """Find citations in *text*, richest kinds first.

    Overlapping matches are resolved by preferring the more specific kind —
    a regional reporter cite parallel to an ND medium-neutral cite is folded
    into the ND one rather than reported twice.
    """
    if not text:
        return []

    marks = _paragraph_index(text)
    found: list[Citation] = []
    claimed: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(s < ce and e > cs for cs, ce in claimed)

    def add(m: re.Match, kind: str, pinpoint: Optional[str] = None,
            normalized: str = "") -> None:
        s, e = m.start(), m.end()
        if overlaps(s, e):
            return
        pin = pinpoint
        if pin is None:
            tail = _PINPOINT_RE.match(text[e:e + 40])
            pin = _normalize_space(tail.group("pin")) if tail else None
        claimed.append((s, e))
        found.append(Citation(
            raw=_normalize_space(m.group(0)),
            kind=kind,
            start=s,
            end=e,
            normalized=normalized or _normalize_space(m.group(0)),
            antecedent_name=_antecedent_name(text, s) if kind == ND_CASE else None,
            pinpoint=pin,
            proposition=_sentence_around(text, s, e, _normalize_space(m.group(0))),
            quotation=_quotation_near(text, s, e),
            paragraph=_paragraph_for(s, marks),
        ))

    for m in _ND_CASE_RE.finditer(text):
        court = " ND App " if m.group("app") else " ND "
        add(m, ND_CASE,
            normalized=f"{m.group('year')}{court}{m.group('num')}")

    for m in _ND_STATUTE_RE.finditer(text):
        sub = m.group("sub") or ""
        add(m, ND_STATUTE, pinpoint=sub or None,
            normalized=f"N.D.C.C. § {m.group('num')}{sub}")

    for m in _ND_RULE_RE.finditer(text):
        rule_set = re.sub(r"[.\s]", "", m.group("set")).lower()
        label = {"appp": "N.D.R.App.P.", "ct": "N.D.R.Ct.", "civp": "N.D.R.Civ.P.",
                 "crimp": "N.D.R.Crim.P.", "ev": "N.D.R.Ev."}.get(rule_set, "N.D.R.")
        sub = m.group("sub") or ""
        add(m, ND_RULE, pinpoint=sub or None,
            normalized=f"{label} {m.group('num')}{sub}")

    for m in _REGIONAL_RE.finditer(text):
        add(m, REGIONAL)

    for m in _FOREIGN_RE.finditer(text):
        add(m, FOREIGN)

    found.sort(key=lambda c: c.start)
    return _fold_parallel_cites(text, found)


# Gap allowed between an ND cite (with any pinpoint) and its parallel
# regional reporter cite: ", ¶ 9, " and the like.
_PARALLEL_GAP_RE = re.compile(r"^[\s,]*(?:(?:¶{1,2}|paras?\.?)\s*[\d\s,–-]*)?[\s,]*$")


def _fold_parallel_cites(text: str, cites: list[Citation]) -> list[Citation]:
    """Drop regional cites that merely parallel an adjacent ND case cite.

    "Torgerson v. Bexley, 2024 ND 88, ¶ 9, 1002 N.W.2d 44" is one authority
    under two citation forms, and Rule 11.6 requires both.  Counting it
    twice would inflate the coverage line and send two lookups for one case.
    A regional cite standing alone still counts — a pre-1997 ND decision has
    no medium-neutral form.
    """
    kept: list[Citation] = []
    for cite in cites:
        if cite.kind == REGIONAL and kept:
            prev = kept[-1]
            gap = text[prev.end:cite.start]
            if prev.kind == ND_CASE and _PARALLEL_GAP_RE.match(gap):
                prev.parallel_cite = cite.raw
                continue
        kept.append(cite)
    return kept


# --- Scoping ----------------------------------------------------------------

# A brief can carry a hundred citations.  Retrieval is the expensive step, so
# the pass is capped and the cap is disclosed rather than silently applied.
DEFAULT_LOOKUP_CAP = 40


@dataclass
class GroundingScope:
    """What the grounding pass will attempt, and what it will not.

    Every citation found lands in exactly one bucket, so the coverage line
    adds up and "not checked" never reads as "checked and sound".
    """

    selected: list[Citation] = field(default_factory=list)
    unverifiable: list[Citation] = field(default_factory=list)   # outside ndlaw
    low_value: list[Citation] = field(default_factory=list)      # no pinpoint, no quote
    over_cap: list[Citation] = field(default_factory=list)       # excluded by the cap

    @property
    def total(self) -> int:
        return (len(self.selected) + len(self.unverifiable)
                + len(self.low_value) + len(self.over_cap))

    def coverage_line(self) -> str:
        """One sentence stating what was attempted, before any findings."""
        parts = [f"Found {self.total} citation(s); "
                 f"{len(self.selected)} selected for verification"]
        if self.unverifiable:
            parts.append(
                f"{len(self.unverifiable)} outside North Dakota authority and "
                f"not checked")
        if self.low_value:
            parts.append(
                f"{len(self.low_value)} cited without a pinpoint or quotation "
                f"and not checked")
        if self.over_cap:
            parts.append(
                f"{len(self.over_cap)} beyond the {DEFAULT_LOOKUP_CAP}-citation "
                f"cap and not checked")
        return "; ".join(parts) + ". Unchecked citations are unverified, not confirmed."

    def to_dict(self) -> dict:
        return {
            "coverage_line": self.coverage_line(),
            "total": self.total,
            "selected": [c.to_dict() for c in self.selected],
            "excluded": {
                "unverifiable": [c.to_dict() for c in self.unverifiable],
                "low_value": [c.to_dict() for c in self.low_value],
                "over_cap": [c.to_dict() for c in self.over_cap],
            },
        }


def select_for_grounding(
    citations: list[Citation],
    cap: int = DEFAULT_LOOKUP_CAP,
) -> GroundingScope:
    """Choose which citations are worth retrieving.

    Three rules, in order:

    * An authority outside ndlaw's reach cannot be verified here at all.
    * A citation carrying a pinpoint or quoted matter can be tested against
      the text it points to.  One without either supports a proposition only
      generally — a string cite — and retrieving it proves little.
    * Beyond the cap, nothing more is attempted.

    Quoted matter is never dropped for want of a pinpoint: a misquotation is
    checkable on its own, and it is the failure mode with the sharpest
    consequences.
    """
    scope = GroundingScope()
    ranked: list[Citation] = []

    for cite in citations:
        if not cite.verifiable:
            scope.unverifiable.append(cite)
        elif cite.quotation or cite.pinpoint:
            ranked.append(cite)
        else:
            scope.low_value.append(cite)

    # Quotations first — a misquotation is the sharpest finding, so it should
    # survive the cap when a bare pinpoint would not.
    ranked.sort(key=lambda c: (c.quotation is None, c.pinpoint is None, c.start))
    scope.selected = ranked[:cap]
    scope.over_cap = ranked[cap:]
    return scope
