"""Rule thresholds and patterns for ND Rules of Appellate Procedure compliance."""

from core.models import BriefType

# --- Page dimensions (inches) ---
PAPER_WIDTH = 8.5
PAPER_HEIGHT = 11.0
PAPER_TOLERANCE = 0.1  # allow small deviation

# --- Margin minimums (inches) ---
MIN_LEFT_MARGIN = 1.5
MIN_RIGHT_MARGIN = 1.0
MIN_TOP_MARGIN = 1.0
MIN_BOTTOM_MARGIN = 1.0
MARGIN_TOLERANCE = 0.05  # small tolerance for measurement imprecision

# --- Font ---
MIN_FONT_SIZE_PT = 12.0
MAX_CHARS_PER_INCH = 16
FONT_SIZE_TOLERANCE = 0.3  # pt tolerance for font size detection
FONT_NONCOMPLIANT_THRESHOLD = 10  # chars per page: >= this count is REJECT, below is NOTE

# --- Spacing ---
# Double spacing is ~24pt between baselines for 12pt text.
# We allow some tolerance: anything >= 20pt is "double-spaced."
MIN_DOUBLE_SPACE_PTS = 20.0

# --- Page limits ---
PAGE_LIMITS = {
    BriefType.APPELLANT: 38,
    BriefType.APPELLEE: 38,
    BriefType.CROSS_APPEAL: 38,
    BriefType.REPLY: 12,
    BriefType.AMICUS: 19,
}

# Word limit for amicus rehearing brief
AMICUS_REHEARING_WORD_LIMIT = 2600

# --- Cover color by brief type ---
# Rule 32(a)(2): colors for brief covers
COVER_COLORS = {
    BriefType.APPELLANT: "blue",
    BriefType.APPELLEE: "red",
    BriefType.REPLY: "gray",
    BriefType.CROSS_APPEAL: "gray",
    BriefType.AMICUS: "green",
}

# --- Section heading patterns ---
# Regex patterns to detect key brief sections in text.
# Used by both mechanical and semantic checks.
SECTION_PATTERNS = {
    "table_of_contents": r"(?i)table\s+of\s+contents",
    "table_of_authorities": r"(?i)table\s+of\s+authorities",
    "jurisdictional_statement": r"(?i)jurisdictional\s+statement|statement\s+of\s+jurisdiction",
    "statement_of_issues": r"(?i)statement\s+of\s+(the\s+)?issues?|issues?\s+presented",
    "statement_of_case": r"(?i)statement\s+of\s+(the\s+)?case",
    "statement_of_facts": r"(?i)statement\s+of\s+(the\s+)?facts",
    "argument": r"(?i)^argument\b|\bargument\s*$",
    "standard_of_review": r"(?i)standard\s+of\s+review",
    "conclusion": r"(?i)^conclusion\b|\bconclusion\s*$",
    "certificate_of_compliance": r"(?i)certificate\s+of\s+compliance",
    "addendum": r"(?i)^addendum\b|\baddendum\s*$",
}

# Brief type detection is handled in brief_classifier.py with fuzzy matching.

# --- Addendum detection ---
ADDENDUM_PATTERN = r"(?i)^\s*addendum\s*$"
