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

# Case names run left from the "v." across more than capitalised words:
# "Davis o/b/o HJR & CER v. Romanyshyn", "State ex rel. Smith v. Jones",
# "Olson et al. v. Berg".  Truncating at a connector produces a fragment, and
# a fragment compared against the canonical name reads as name drift — a
# false flag on a correctly cited case.
#
# The connectors are spelled in both cases explicitly rather than with the
# IGNORECASE flag: the flag would also let [A-Z] match lowercase, and the
# name would then walk left through ordinary prose and swallow the sentence.
_NAME_CONNECTOR = (
    r"(?:o/b/o|O/B/O|ex\s+rel\.?|Ex\s+rel\.?|et\s+al\.?|Et\s+al\.?|&|"
    r"on\s+behalf\s+of|In\s+re|in\s+re)"
)
_NAME_WORD = r"[A-Z][\w.'’-]*"
_NAME_TOKEN = rf"(?:{_NAME_WORD}|{_NAME_CONNECTOR})"
_CASE_NAME_RE = re.compile(
    rf"(?P<name>{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})*"
    r"\s+v\.?\s+"
    rf"{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})*?)"
    r"[\s,]*$"
)

# A quotation of at least a few words, straight or curly
_QUOTE_RE = re.compile(r"[\"“]([^\"”]{12,600})[\"”]")

# Brief paragraph markers.  Rule 32(a)(7) requires arabic paragraph numbers
# but not a particular decoration, and real briefs use several: "[12]",
# "¶ 12", and "[¶ 12]".  Missing a form collapses the paragraph bounds, which
# is what confines a quotation to its own citation — so all are matched.
_BRIEF_PARA_RE = re.compile(
    r"(?:^|\n)\s*(?:\[\s*¶?\s*(\d{1,4})\s*\]|¶+\s*(\d{1,4}))")

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
    if starts:
        para_start = max((s for s in starts if s <= offset), default=0)
        para_end = min((s for s in starts if s > offset), default=len(text))
        return para_start, para_end

    # No numbered paragraphs — Rule 32(a)(7) requires them, but the checker
    # still has to work on a brief that omits them.  A blank-line split is
    # unreliable here: extraction inserts blank lines at page breaks, which
    # can fall inside a quotation and hide it from the citation it belongs
    # to.  Use a plain window instead.
    return max(0, offset - 900), min(len(text), offset + 400)


def _quotation_near(text: str, start: int, end: int) -> Optional[str]:
    """Quoted matter attributable to a citation.

    A brief may quote before citing ("...," the court held, Smith, 2020 ND 1)
    or after (Smith, 2020 ND 1 ("the text")).  Both are searched, but only
    within the citation's own paragraph: quoted matter three paragraphs
    away is somebody else's.
    """
    para_start, para_end = _paragraph_bounds(text, start)

    # Look back only as far as the closing quotation mark, and only accept it
    # when what sits between the quote and the cite is citation apparatus —
    # a case name, a signal, punctuation.  A paragraph carrying several cites
    # otherwise hands every one of them the first quotation in the paragraph.
    before = text[max(para_start, start - 900):start]
    matches = list(_QUOTE_RE.finditer(before))
    if matches:
        last = matches[-1]
        between = before[last.end():]
        if _CITE_APPARATUS_RE.fullmatch(between.strip()) is not None:
            return _clean_quote(last.group(1))

    # A quotation *after* a citation belongs to it only when it sits in a
    # parenthetical attached to the cite — Smith, 2020 ND 1 ("the text").
    # Otherwise the quotation introduces the next citation, and attributing
    # it here shifts every quote in a string of citations one place.
    after = text[end:min(para_end, end + 300)]
    matches = list(_QUOTE_RE.finditer(after))
    gap = after[:matches[0].start()] if matches else ""
    if matches and re.fullmatch(r"[\s,]*(?:¶+\s*[\d\s,–-]*)?[\s,]*\(\s*", gap):
        return _clean_quote(matches[0].group(1))
    return None


# What may legitimately sit between a quotation and the citation it belongs
# to: a case name, a signal, a pinpoint, punctuation.  Tokens are separated,
# so the separator has to be part of the repetition — without it, "State v.
# P.K.," fails to match and every quotation is silently dropped.
_APPARATUS_TOKEN = (
    r"(?:[A-Z][\w.'’-]*|v\.?|see|also|accord|cf\.?|e\.?g\.?|quoting|citing|"
    r"internal|citations?|omitted|ex|rel\.?|et|al\.?|o/b/o|in|re|at|id\.?|"
    r"supra|¶+|\d+|N\.?W\.?\s?\d?d?|N\.?D\.?)"
)
_CITE_APPARATUS_RE = re.compile(
    rf"(?:[\s,;.()\[\]&’'\"“”-]*{_APPARATUS_TOKEN})*[\s,;.()\[\]-]*"
)

# A page number lands in the middle of extracted text and breaks a quotation
# that is otherwise verbatim.
_STRAY_PAGE_NUM_RE = re.compile(r"\s+\d{1,3}\s+(?=[a-z])")


def _clean_quote(raw: str) -> str:
    """Normalize a quotation and drop page numbers extraction left inside it."""
    return _normalize_space(_STRAY_PAGE_NUM_RE.sub(" ", _normalize_space(raw)))


# Words that only appear in a brief's section headings, never inside a case
# name.  Used to stop an antecedent-name walk from crossing a heading.
_HEADING_WORDS = {
    "TABLE", "TABLES", "AUTHORITIES", "CONTENTS", "CASES", "STATUTES",
    "RULES", "ARGUMENT", "STATEMENT", "CONCLUSION", "INTRODUCTION", "FACTS",
    "ISSUES", "APPENDIX", "ADDENDUM", "CERTIFICATE", "COMPLIANCE", "SERVICE",
    "JURISDICTION", "SUMMARY", "SECONDARY", "OTHER",
}


def _antecedent_name(text: str, start: int) -> Optional[str]:
    """The case name immediately before a citation, if any."""
    window = text[max(0, start - 200):start]
    m = _CASE_NAME_RE.search(_normalize_space(window))
    if not m:
        return None
    name = _normalize_space(m.group("name"))
    # A brief's section headings read as runs of capitalised words, so the
    # walk left can cross out of the sentence and into "TABLE OF AUTHORITIES
    # Cases Davis o/b/o ... v. Romanyshyn".  Cut after the last heading word.
    #
    # Detecting headings by capitalisation alone does not work: party initials
    # are legitimately capitalised too, and "HJR & CER" would be mistaken for
    # shouting and the real name discarded.  Match a heading vocabulary.
    tokens = name.split()
    last_heading = max(
        (i for i, tok in enumerate(tokens)
         if tok.strip(".,:").upper() in _HEADING_WORDS),
        default=None,
    )
    if last_heading is not None:
        name = " ".join(tokens[last_heading + 1:])
    if " v" not in name.lower():
        return None
    # Guard against swallowing a lead-in verb or signal
    name = re.sub(
        r"^(?:see(?:\s+(?:also|generally))?|accord|cf\.?|e\.?g\.?|but\s+see|citing|"
        r"quoting|contra|compare|the\s+court\s+in|as\s+articulated\s+in|"
        r"this\s+Court\s+(?:ruled|held)\s+in|and|of|the)\s+",
        "", name, flags=re.IGNORECASE).strip()
    # A name must still contain the "v." anchor after stripping
    if " v" not in name.lower():
        return None
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

    selected: list[Citation] = field(default_factory=list)        # distinct authorities
    quotations: list[Citation] = field(default_factory=list)      # occurrences with quotes
    unverifiable: list[Citation] = field(default_factory=list)    # outside ndlaw
    duplicate: list[Citation] = field(default_factory=list)       # same authority again
    over_cap: list[Citation] = field(default_factory=list)        # excluded by the cap

    @property
    def total(self) -> int:
        return (len(self.selected) + len(self.unverifiable)
                + len(self.duplicate) + len(self.over_cap))

    def coverage_line(self) -> str:
        """One sentence stating what was attempted, before any findings."""
        authorities = len(self.selected)
        quotes = len(self.quotations)
        parts = [
            f"Found {self.total} citation(s) to "
            f"{authorities + len(self.over_cap)} distinct "
            f"authorit{'y' if authorities + len(self.over_cap) == 1 else 'ies'}; "
            f"{authorities} checked for existence and case name"
        ]
        if quotes:
            parts.append(f"{quotes} quotation(s) checked against the opinion text")
        if self.duplicate:
            parts.append(
                f"{len(self.duplicate)} repeat citation(s) covered by the check "
                f"of the same authority")
        if self.unverifiable:
            parts.append(
                f"{len(self.unverifiable)} outside North Dakota authority and "
                f"not checked")
        if self.over_cap:
            parts.append(
                f"{len(self.over_cap)} beyond the {DEFAULT_LOOKUP_CAP}-authority "
                f"cap and not checked")
        return ("; ".join(parts) + ". Whether an authority supports the proposition "
                "it is cited for was not assessed. Unchecked citations are "
                "unverified, not confirmed.")

    def to_dict(self) -> dict:
        return {
            "coverage_line": self.coverage_line(),
            "total": self.total,
            "selected": [c.to_dict() for c in self.selected],
            "excluded": {
                "unverifiable": [c.to_dict() for c in self.unverifiable],
                "duplicate": [c.to_dict() for c in self.duplicate],
                "over_cap": [c.to_dict() for c in self.over_cap],
            },
        }


def _authority_key(cite: Citation) -> str:
    """Identity of the authority a citation points to.

    A subsection is a pinpoint into an authority, not a separate one:
    "N.D.R.Ev. 201" and "N.D.R.Ev. 201(b)" are the same rule, and checking
    both would spend two lookups to answer one question.
    """
    return re.sub(r"\([^)]*\)", "", cite.normalized).strip().lower()


def select_for_grounding(
    citations: list[Citation],
    cap: int = DEFAULT_LOOKUP_CAP,
) -> GroundingScope:
    """Choose which citations to verify.

    The pass asks two questions, neither of which needs a pinpoint:

    * Does this authority exist, and is it the case the brief names?
    * Is the quoted matter accurate?

    So every North Dakota authority is worth checking, not only those cited
    with a pinpoint.  Existence is a property of the authority rather than of
    the occurrence, so repeat citations of the same case ride on the first
    check — but an occurrence carrying its own quotation is kept, because a
    second quotation from the same case is a second thing to verify.

    Authority outside ndlaw's reach cannot be checked here at all, and beyond
    the cap nothing further is attempted.  Both are reported.
    """
    scope = GroundingScope()
    seen: set[str] = set()
    ranked: list[Citation] = []

    for cite in citations:
        if not cite.verifiable:
            scope.unverifiable.append(cite)
            continue
        # Each occurrence carrying quoted matter is its own thing to verify,
        # even when the authority has already been seen.
        if cite.quotation:
            scope.quotations.append(cite)
        key = _authority_key(cite)
        if key in seen:
            scope.duplicate.append(cite)
            continue
        seen.add(key)
        ranked.append(cite)

    # Authorities carrying a quotation first: a misquotation is the sharper
    # finding, so it should survive the cap ahead of a bare existence check.
    ranked.sort(key=lambda c: (c.quotation is None, c.start))
    scope.selected = ranked[:cap]
    scope.over_cap = ranked[cap:]
    return scope


# --- Review results (produced by the retrieval phase, consumed by the report) ---

# Classifications, deliberately including the ones that record a non-answer.
EXISTS_CONFIRMED = "confirmed"
EXISTS_NOT_FOUND = "not_found"
UNCHECKED = "unchecked"

# Whether a passage actually supports the proposition it is cited for is
# deliberately OUT OF SCOPE.  That judgment needs the retrieved paragraph read
# against the brief's argument, and its hard case — partial support — has not
# been validated against real briefs.  The constants stay so the field can be
# populated later without a schema change, but nothing sets them and nothing
# flags on them: the pass answers only "does this authority exist, is it the
# case the brief names, and is the quotation accurate".
SUPPORTS = "supports"
PARTIALLY_SUPPORTS = "partially_supports"
DOES_NOT_SUPPORT = "does_not_appear_to_support"
COULD_NOT_RETRIEVE = "could_not_retrieve"
NOT_ASSESSED = "not_assessed"

# Below this name similarity, a mismatch is worth raising.  ndlaw compares
# the name as written against a canonical short form, so a legitimate longer
# style scores well short of 1.0 without being wrong: a real brief citing
# "Davis o/b/o HJR & CER v. Romanyshyn" scores 0.667 against the canonical
# "Davis, et al. v. Romanyshyn" — the same case, correctly cited. Flagging on
# any mismatch would fire on that. A genuinely wrong case shares little.
NAME_SIMILARITY_FLOOR = 0.5

QUOTE_VERBATIM = "verbatim"
QUOTE_ALTERED = "altered"
QUOTE_NOT_FOUND = "not_found"

# Outcomes worth a reader's attention.  Everything else is either sound or
# openly unchecked, and neither needs a per-citation entry in the report.
_FLAGGED_EXISTENCE = {EXISTS_NOT_FOUND}
_FLAGGED_QUOTATION = {QUOTE_ALTERED, QUOTE_NOT_FOUND}


@dataclass
class CitationFinding:
    """The result of checking one citation against the retrieved authority."""

    cite: str
    proposition: str = ""
    pinpoint: Optional[str] = None
    antecedent_name: Optional[str] = None
    brief_paragraph: Optional[int] = None
    quotation: Optional[str] = None
    exists: str = UNCHECKED
    name_matches: Optional[bool] = None
    name_similarity: Optional[float] = None
    canonical_name: Optional[str] = None
    quotation_result: Optional[str] = None
    support: str = NOT_ASSESSED
    retrieved_excerpt: str = ""
    reason: str = ""

    @property
    def name_drifted(self) -> bool:
        """True when the name difference looks like more than style.

        Naming the same case a longer way is not an error, so a mismatch
        only counts when the names barely resemble each other.
        """
        if self.name_matches is not False:
            return False
        if self.name_similarity is None:
            return True
        return self.name_similarity < NAME_SIMILARITY_FLOOR

    @property
    def flagged(self) -> bool:
        """True when this citation is worth a reader's attention.

        A wrong case name on a real citation counts: the authority exists,
        but it is not the one the brief says it is.  A merely stylistic
        difference in the name does not — see NAME_SIMILARITY_FLOOR.

        Proposition support is not consulted: it is out of scope, and a
        classification nothing produces must not silently gate anything.
        """
        return (
            self.exists in _FLAGGED_EXISTENCE
            or self.name_drifted
            or self.quotation_result in _FLAGGED_QUOTATION
        )

    @classmethod
    def from_dict(cls, d: dict) -> "CitationFinding":
        return cls(
            cite=d.get("cite", ""),
            proposition=d.get("proposition", ""),
            pinpoint=d.get("pinpoint"),
            antecedent_name=d.get("antecedent_name"),
            brief_paragraph=d.get("brief_paragraph"),
            quotation=d.get("quotation"),
            exists=d.get("exists", UNCHECKED),
            name_matches=d.get("name_matches"),
            name_similarity=d.get("name_similarity"),
            canonical_name=d.get("canonical_name"),
            quotation_result=d.get("quotation_result"),
            support=d.get("support", NOT_ASSESSED),
            retrieved_excerpt=d.get("retrieved_excerpt", ""),
            reason=d.get("reason", ""),
        )


@dataclass
class CitationReview:
    """The citation-grounding pass as a whole.

    Advisory throughout.  Rule compliance is governed by the appellate rules;
    whether an authority says what the brief says it says is a different
    question, and it must not move the Accept / Correction Letter / Reject
    recommendation.  Nothing here is a CheckResult for that reason.
    """

    ndlaw_available: bool = True
    coverage_line: str = ""
    findings: list[CitationFinding] = field(default_factory=list)
    unavailable_reason: str = ""

    @property
    def flagged(self) -> list[CitationFinding]:
        return [f for f in self.findings if f.flagged]

    @property
    def clear(self) -> list[CitationFinding]:
        return [f for f in self.findings if not f.flagged]

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
    def from_dict(cls, d: dict) -> "CitationReview":
        if not d.get("ndlaw_available", True):
            review = cls.unavailable(d.get("unavailable_reason", ""))
            if d.get("coverage_line"):
                review.coverage_line = d["coverage_line"]
            return review
        return cls(
            ndlaw_available=True,
            coverage_line=d.get("coverage_line", ""),
            findings=[CitationFinding.from_dict(f) for f in d.get("findings", [])],
        )
