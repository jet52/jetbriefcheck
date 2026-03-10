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

from core.models import BriefMetadata, BriefType


def classify_brief(metadata: BriefMetadata) -> BriefType:
    """Determine brief type from cover page text.

    Three-pass approach:
      Pass 0: Check for "petition for rehearing" — this is distinctive
              and should be detected before any brief-type logic.
      Pass 1: Look for "X brief" or "brief of X" phrases — this is the
              primary signal and avoids false matches on party labels.
      Pass 2: Fall back to standalone party labels only if pass 1 finds nothing.

    Priority within each pass: amicus > reply > cross-appeal > appellee > appellant.
    """
    text = _normalize(metadata.cover_text)

    # ---- Pass 0: petition for rehearing ----
    if _match_petition_rehearing(text):
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


# ---------------------------------------------------------------------------
# Pass 1: Match "X brief" / "brief of X" phrases
# ---------------------------------------------------------------------------

def _match_brief_phrase(text: str) -> BriefType:
    """Look for party-type words adjacent to 'brief'."""

    # --- Amicus ---
    if re.search(rf"am[il1!|].?c[ue][sz].{{0,20}}{_BR}", text):
        return BriefType.AMICUS
    if re.search(rf"{_BR}.{{0,20}}am[il1!|].?c[ue][sz]", text):
        return BriefType.AMICUS
    if re.search(rf"friend.{{0,5}}(of\s+)?(the\s+)?court.{{0,15}}{_BR}", text):
        return BriefType.AMICUS
    if re.search(rf"{_BR}.{{0,15}}friend.{{0,5}}(of\s+)?(the\s+)?court", text):
        return BriefType.AMICUS
    # "amicus brief" (without "curiae")
    if re.search(rf"am[il1!|].?c[ue][sz]\s+{_BR}", text):
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

    # For appellant/appellee, we must be careful: covers list BOTH parties.
    # Strategy: find "brief" and look at what's immediately adjacent.
    # Handles compound designations like "defendant-appellant" or "plaintiff-appellee".

    # "brief of ..." direction — grab a few words after "brief of (the)"
    m = re.search(rf"{_BR}\s+of\s+(the\s+)?(.{{1,40}}?)(?:\s*[,\n]|\s{{2,}}|$)", text)
    if m:
        after = m.group(2)
        # Cross-appeal takes priority (compound: "cross-appellant and appellee")
        if re.search(r"cross[- ]?app?e[il1!|]{1,2}[ae]", after):
            return BriefType.CROSS_APPEAL
        # Check for appellee/respondent first (more specific than appellant)
        if re.search(_p_appellee(), after) or re.search(_p_respondent(), after):
            return BriefType.APPELLEE
        if re.search(_p_appellant(), after) or re.search(_p_petitioner(), after):
            return BriefType.APPELLANT

    # "X brief" direction — grab compound words before "brief"
    m = re.search(rf"(\S+(?:-\S+)*)\s+{_BR}", text)
    if m:
        before = m.group(1)
        if re.search(_p_appellee(), before) or re.search(_p_respondent(), before):
            return BriefType.APPELLEE
        if re.search(_p_appellant(), before) or re.search(_p_petitioner(), before):
            return BriefType.APPELLANT

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
