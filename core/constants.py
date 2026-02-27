"""Rule thresholds and patterns for Iowa Rules of Appellate Procedure compliance."""

from core.models import BriefType

# --- Page dimensions (inches) ---
PAPER_WIDTH = 8.5
PAPER_HEIGHT = 11.0
PAPER_TOLERANCE = 0.1  # allow small deviation

# --- Margin minimums (inches) ---
# Iowa R. App. P. 6.903(1)(d): at least 1 inch on all sides
MIN_LEFT_MARGIN = 1.0
MIN_RIGHT_MARGIN = 1.0
MIN_TOP_MARGIN = 1.0
MIN_BOTTOM_MARGIN = 1.0
MARGIN_TOLERANCE = 0.05  # small tolerance for measurement imprecision

# --- Font ---
# Iowa R. App. P. 6.903(1)(e): 14-point proportionally spaced serif typeface,
# or monospaced typeface no more than 10.5 characters per inch
MIN_FONT_SIZE_PT = 14.0
MAX_CHARS_PER_INCH = 10  # monospaced: 10.5 cpi max, rounded down for safety
FONT_SIZE_TOLERANCE = 0.3  # pt tolerance for font size detection
FONT_NONCOMPLIANT_THRESHOLD = 10  # chars per page: >= this count is REJECT, below is NOTE

# Small caps detection — font size check should not penalize
# conventional small-caps formatting (headings, citations, cover page, signatures).
SMALL_CAPS_SIZE_RATIO_MIN = 0.55  # smallest ratio of span size to body font
SMALL_CAPS_SIZE_RATIO_MAX = 0.85  # largest ratio (above this it's near full-size)
SMALL_CAPS_SUSPICIOUS_PAGE_PCT = 15.0  # % of page chars; above this, small caps on
                                        # non-conventional pages are treated as body text

# --- Spacing ---
# Double spacing is ~28pt between baselines for 14pt text.
# We allow some tolerance: anything >= 24pt is "double-spaced."
MIN_DOUBLE_SPACE_PTS = 24.0

# --- Word count limits ---
# Iowa R. App. P. 6.903(1)(g)(1): type-volume limitations by word count
# (for proportionally spaced typeface)
WORD_LIMITS = {
    BriefType.APPELLANT: 14000,
    BriefType.APPELLEE: 14000,
    BriefType.CROSS_APPEAL: 14000,
    BriefType.REPLY: 7000,
    BriefType.AMICUS: 7000,
}

# Iowa does not use page limits; word count is the primary length constraint.
# We keep PAGE_LIMITS for backward compatibility but set them to None.
PAGE_LIMITS = {
    BriefType.APPELLANT: None,
    BriefType.APPELLEE: None,
    BriefType.CROSS_APPEAL: None,
    BriefType.REPLY: None,
    BriefType.AMICUS: None,
}

# Line limits for monospaced typeface briefs
# Iowa R. App. P. 6.903(1)(g)(2)
LINE_LIMITS = {
    BriefType.APPELLANT: 1300,
    BriefType.APPELLEE: 1300,
    BriefType.CROSS_APPEAL: 1300,
    BriefType.REPLY: 650,
    BriefType.AMICUS: 650,
}

# --- Cover colors ---
# Iowa files briefs electronically via EDMS; no physical cover color requirement.
# The court affixes covers for printed copies. We keep the dict for compatibility
# but mark all as None (no color check performed).
COVER_COLORS = {
    BriefType.APPELLANT: None,
    BriefType.APPELLEE: None,
    BriefType.REPLY: None,
    BriefType.CROSS_APPEAL: None,
    BriefType.AMICUS: None,
}

# --- Section heading patterns ---
# Regex patterns to detect key brief sections in text.
# Updated for Iowa-specific section names.
SECTION_PATTERNS = {
    "table_of_contents": r"(?i)table\s+of\s+contents",
    "table_of_authorities": r"(?i)table\s+of\s+authorities",
    "routing_statement": r"(?i)routing\s+statement",
    "statement_of_issues": r"(?i)statement\s+of\s+(the\s+)?issues?|issues?\s+presented",
    "statement_of_case": r"(?i)statement\s+of\s+(the\s+)?case",
    "statement_of_facts": r"(?i)statement\s+of\s+(the\s+)?facts",
    "argument": r"(?i)^argument\b|\bargument\s*$",
    "standard_of_review": r"(?i)standard\s+of\s+review|scope\s+of\s+review",
    "preservation_of_error": r"(?i)preserv(ation|ed)\s+(of\s+)?error|error\s+preserv(ation|ed)",
    "conclusion": r"(?i)^conclusion\b|\bconclusion\s*$",
    "certificate_of_compliance": r"(?i)certificate\s+of\s+compliance",
    "request_for_oral_argument": r"(?i)(request\s+for\s+)?oral\s+argument",
    "certificate_of_filing": r"(?i)certificate\s+of\s+(filing|service)",
}

# Brief type detection is handled in brief_classifier.py with fuzzy matching.
