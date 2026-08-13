"""Classify brief type from cover page text.

Uses aggressive text normalization and fuzzy matching to handle:
- Unicode curly quotes, smart quotes, backticks
- Zero-width characters, ligatures, odd whitespace
- Misspellings (appel*a*nt vs appel*e*nt, etc.)
- With or without apostrophe-s ("appellant's" / "appellants" / "appellant")
- Reordered phrasing ("brief of appellant" / "appellant brief")
- OCR artifacts and unusual fonts
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from core.models import BriefMetadata, BriefType


def classify_brief(metadata: BriefMetadata) -> BriefType:
    """Determine brief type from cover page text.

    Three-pass approach:
      Pass 0: Check for "petition for rehearing" — this is distinctive
              and should be detected before any brief-type logic. An amicus
              brief filed on rehearing names the petition on its cover too,
              so an amicus signal there wins: Rule 29(b) governs it, not
              Rule 40.
      Pass 1: Look for "X brief" or "brief of X" phrases — this is the
              primary signal and avoids false matches on party labels.
      Pass 2: Fall back to standalone party labels only if pass 1 finds nothing.

    Priority within each pass: amicus > reply > cross-appeal > appellee > appellant.
    """
    text = _normalize(metadata.cover_text)

    # ---- Pass 0: petition for rehearing ----
    if _match_petition_rehearing(text):
        if _match_amicus(text):
            return BriefType.AMICUS_REHEARING
        return BriefType.PETITION_REHEARING

    # ---- Pass 1: phrases tied to "brief" ----
    result = _match_brief_phrase(text)
    if result != BriefType.UNKNOWN:
        return result

    # ---- Pass 2: standalone party labels (fallback) ----
    return _match_standalone(text)


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Aggressively normalize text for fuzzy matching."""
    # NFKD: decomposes characters (e.g., fi → fi, fl → fl)
    text = unicodedata.normalize("NFKD", text)

    # Strip combining characters (accents, diacritics)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Remove zero-width characters
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)

    # Fix common ligature residues that NFKD doesn't fully handle:
    # fi ligature (U+FB01) → NFKD → "fi", but inside "brief" it produces "brifi"
    # fl ligature (U+FB02) → NFKD → "fl"
    # These are already handled, but fix compound artifacts:
    text = re.sub(r"brifi[f]?", "brief", text, flags=re.IGNORECASE)
    text = re.sub(r"bri[eé]f", "brief", text, flags=re.IGNORECASE)

    # Replace all quote-like characters with empty string
    text = re.sub(r"['\u2018\u2019\u201a\u201b`\u0060\u00b4\u2032\u2035]", "", text)
    text = re.sub(r'["\u201c\u201d\u201e\u201f\u00ab\u00bb\u2033\u2036]', "", text)

    # Replace all dash-like characters with hyphen
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d]", "-", text)

    text = text.lower().strip()

    # Collapse letter-spacing BEFORE collapsing whitespace, so multi-space
    # word boundaries are preserved.
    text = _collapse_letter_spacing(text)

    # Now collapse remaining whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _collapse_letter_spacing(text: str) -> str:
    """Collapse letter-spaced words like 'a p p e l l a n t' → 'appellant'.

    Detects sequences of 3+ single letters separated by single spaces.
    Multi-space gaps (2+ spaces, tabs, newlines) are treated as word boundaries.
    """
    # Replace multi-space word boundaries with a sentinel
    sentinel = "\x00"
    result = re.sub(r" {2,}|\t|\n", sentinel, text)

    # Now collapse single-letter runs separated by single spaces
    def _join_letters(m: re.Match) -> str:
        return m.group(0).replace(" ", "")

    result = re.sub(r"(?:[a-zA-Z] ){2,}[a-zA-Z]", _join_letters, result)

    # Restore sentinels as spaces
    return result.replace(sentinel, " ")


# ---------------------------------------------------------------------------
# Fuzzy building blocks
# ---------------------------------------------------------------------------

# Character classes for OCR/ligature confusion
_LL = r"(?:[il1!|f]{1,2})"     # l, ll, or fl-ligature residue
_IL = r"[il1!|]"               # single i or l
_BR = rf"br[il1!|f]ef"         # "brief"


def _p_appellant() -> str:
    """Regex fragment matching 'appellant(s)' loosely."""
    return rf"a ?p{{1,2}}e{_LL}[ae]nts?"


def _p_appellee() -> str:
    """Regex fragment matching 'appellee(s)' loosely."""
    return rf"app?e{_LL}ees?"


def _p_petitioner() -> str:
    """Regex fragment matching 'petitioner(s)' loosely."""
    return rf"pet{_IL}t{_IL}on[ea]rs?"


def _p_respondent() -> str:
    """Regex fragment matching 'respondent(s)' loosely."""
    return r"resp[oa]n[dt]ents?"


def _p_reply() -> str:
    """Regex fragment matching 'reply' loosely."""
    return rf"rep{_IL}[yi1!|]"


def _p_plaintiff() -> str:
    """Regex fragment matching 'plaintiff(s)' loosely."""
    return rf"p{_IL}a{_IL}nt{_IL}ffs?"


def _p_defendant() -> str:
    """Regex fragment matching 'defendant(s)' loosely."""
    return r"defendants?"


def _p_intervenor() -> str:
    """Regex fragment matching 'intervenor(s)' / 'intervener(s)' loosely."""
    return rf"{_IL}nterven[oae]rs?"


# Party-role words and the brief type each implies.  Trial-court roles imply
# nothing about who is appealing, so they map to None: they anchor a compound
# designation without deciding it.
_ROLE_PATTERNS: list[tuple[str, Optional[BriefType]]] = [
    (_p_appellee(), BriefType.APPELLEE),
    (_p_appellant(), BriefType.APPELLANT),
    (_p_respondent(), BriefType.APPELLEE),
    (_p_petitioner(), BriefType.APPELLANT),
    (_p_plaintiff(), None),
    (_p_defendant(), None),
    (_p_intervenor(), None),
]

# What may join the parts of one designation: a hyphen, slash, dash, or a
# space or two.  Anything longer has left the designation and entered prose.
_DESIGNATION_JOINER = r"[-/\s]{1,3}"


def _designation_role(window: str) -> Optional[BriefType]:
    """Resolve the first party designation in *window* to a brief type.

    A cover names the parties by their trial-court role and their appellate
    role together — "plaintiff-appellant", "respondent - appellant",
    "defendant/appellee".  **The appellate role comes last**, so the trailing
    role governs.  Reading left to right instead resolves
    "respondent - appellant" to appellee, because "respondent" is an
    appellee-side word; that inversion misclassified real briefs.

    Only the *first* cluster of adjacent role words counts.  In "brief of
    appellant in response to appellee", the words are not adjacent, so the
    designation ends at "appellant" and the later mention is ignored.
    """
    hits: list[tuple[int, int, Optional[BriefType]]] = []
    for pattern, brief_type in _ROLE_PATTERNS:
        for match in re.finditer(pattern, window):
            hits.append((match.start(), match.end(), brief_type))
    if not hits:
        return None
    hits.sort()

    cluster = [hits[0]]
    for hit in hits[1:]:
        gap = window[cluster[-1][1]:hit[0]]
        if not re.fullmatch(_DESIGNATION_JOINER, gap):
            break
        cluster.append(hit)

    roles = [bt for _, _, bt in cluster if bt is not None]
    return roles[-1] if roles else None


# ---------------------------------------------------------------------------
# Pass 0: Match "petition for rehearing"
# ---------------------------------------------------------------------------

def _match_petition_rehearing(text: str) -> bool:
    """Detect 'petition for rehearing' on the cover page.

    Handles OCR artifacts, letter-spacing, and common misspellings.
    """
    # "petition for rehearing" — the canonical phrase
    if re.search(r"pet[il1!|]t[il1!|]on\s+for\s+rehear[il1!|]ng", text):
        return True
    # "rehearing petition" (reversed order)
    if re.search(r"rehear[il1!|]ng\s+pet[il1!|]t[il1!|]on", text):
        return True
    return False


def _match_amicus(text: str) -> bool:
    """Detect an amicus curiae brief by an amicus term adjacent to 'brief'.

    Requiring adjacency to "brief" keeps a passing mention of an amicus in
    another party's filing from tipping the classification.
    """
    if re.search(rf"am[il1!|].?c[ue][sz].{{0,20}}{_BR}", text):
        return True
    if re.search(rf"{_BR}.{{0,20}}am[il1!|].?c[ue][sz]", text):
        return True
    if re.search(rf"friend.{{0,5}}(of\s+)?(the\s+)?court.{{0,15}}{_BR}", text):
        return True
    if re.search(rf"{_BR}.{{0,15}}friend.{{0,5}}(of\s+)?(the\s+)?court", text):
        return True
    # "amicus brief" (without "curiae")
    if re.search(rf"am[il1!|].?c[ue][sz]\s+{_BR}", text):
        return True
    return False


# ---------------------------------------------------------------------------
# Pass 1: Match "X brief" / "brief of X" phrases
# ---------------------------------------------------------------------------

def _match_brief_phrase(text: str) -> BriefType:
    """Look for party-type words adjacent to 'brief'."""

    # --- Amicus ---
    if _match_amicus(text):
        return BriefType.AMICUS

    # --- Reply ---
    rpl = _p_reply()
    if re.search(rf"{rpl}.{{0,10}}{_BR}", text):
        return BriefType.REPLY
    if re.search(rf"{_BR}.{{0,10}}(in\s+)?{rpl}", text):
        return BriefType.REPLY

    # --- Cross-appeal ---
    if re.search(rf"cross[- ]?app?e[il1!|]{1,2}[ae].{{0,15}}{_BR}", text):
        return BriefType.CROSS_APPEAL
    if re.search(rf"{_BR}.{{0,15}}cross[- ]?app?e[il1!|]{1,2}[ae]", text):
        return BriefType.CROSS_APPEAL

    # For appellant/appellee, covers name BOTH parties, so resolve the
    # designation attached to "brief" rather than any label on the page.
    #
    # The window is taken without requiring a delimiter to close it.  It used
    # to end at a comma, a newline, or a double space — but _normalize()
    # collapses all whitespace to single spaces before this runs, so on a
    # cover reading "BRIEF OF APPELLANT / APPEAL FROM THE JUDGMENT..." nothing
    # closed the window and the match failed outright. That silently sent the
    # most common cover format in test-data/ to the fallback.

    # "brief of ..." direction
    m = re.search(rf"{_BR}\s+of\s+(?:the\s+)?(.{{1,60}})", text)
    if m:
        after = m.group(1)
        # Cross-appeal takes priority (compound: "cross-appellant and appellee")
        if re.search(r"cross[- ]?app?e[il1!|]{1,2}[ae]", after):
            return BriefType.CROSS_APPEAL
        role = _designation_role(after)
        if role is not None:
            return role

    # "X brief" direction — e.g. "APPELLANT'S BRIEF"
    m = re.search(rf"([\w'-]+(?:[-/][\w'-]+)*)\s+{_BR}", text)
    if m:
        role = _designation_role(m.group(1))
        if role is not None:
            return role

    return BriefType.UNKNOWN


# ---------------------------------------------------------------------------
# Pass 2: Standalone party labels (fallback)
# ---------------------------------------------------------------------------

def _match_standalone(text: str) -> BriefType:
    """Fall back to standalone party labels when no 'brief' phrase is found."""

    # Amicus is distinctive enough standalone
    if re.search(r"am[il1!|].?c[ue][sz]", text):
        return BriefType.AMICUS
    if re.search(r"friend.{0,5}(of\s+)?(the\s+)?court", text):
        return BriefType.AMICUS

    # Cross-appeal
    if re.search(r"cross[- ]?app?e[il1!|]{1,2}[ae]", text):
        return BriefType.CROSS_APPEAL

    # For appellee vs appellant standalone, we can't reliably distinguish
    # because covers list BOTH parties. Don't guess from standalone labels
    # for these — return UNKNOWN and let the user override.

    return BriefType.UNKNOWN
