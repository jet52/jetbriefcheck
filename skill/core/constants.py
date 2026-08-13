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

# Small caps detection — Rule 32(a)(5) font size check should not penalize
# conventional small-caps formatting (headings, citations, cover page, signatures).
SMALL_CAPS_SIZE_RATIO_MIN = 0.55  # smallest ratio of span size to body font
SMALL_CAPS_SIZE_RATIO_MAX = 0.85  # largest ratio (above this it's near full-size)
SMALL_CAPS_SUSPICIOUS_PAGE_PCT = 15.0  # % of page chars; above this, small caps on
                                        # non-conventional pages are treated as body text

# --- Spacing ---
# Double spacing is ~24pt between baselines for 12pt text.
# We allow some tolerance: anything >= 20pt is "double-spaced."
MIN_DOUBLE_SPACE_PTS = 20.0

# Ratio of measured line spacing to predominant font size.  Used only to
# explain a document-wide undersize (FMT-006), never to decide it.
#
# When a page is scaled down, type and leading shrink together, so the ratio
# is unchanged.  When the type alone is undersized, the leading stays full
# size and the ratio rises.  Compliant 12pt briefs in test-data/ cluster
# tightly at 2.30 (27.6pt leading); the two briefs with genuinely undersized
# type sit at 2.85-2.86.  The midpoint separates them with wide margin either
# side.
LEADING_TO_FONT_FULL_SIZE_RATIO = 2.6

# Share of body pages whose line spacing must be measurable before FMT-009
# will state a conclusion.  Below this the median rests on too small a
# sample to distinguish a single-spaced brief from a sampling artifact, and
# the check reports that it could not determine the answer.
#
# Coverage in test-data/ is bimodal: 22 of 23 briefs measure 78-100% of
# their body pages (17 of them 100%), and the one known false negative
# measures 29% — a brief that squeaked past the 20pt threshold at 20.5pt on
# 2 of 7 pages, while its corrected refiling measured 27.6pt on 13 of 13.
# The gap between 29% and 78% is empty, so the floor sits in the middle of
# it rather than on either cluster.
MIN_SPACING_COVERAGE_PCT = 50.0

# Single-spaced runs, reported with FMT-009 but never scored.
#
# A run must reach MIN_REPORTABLE_RUN_LINES to be counted at all — two
# consecutive close baselines are usually a wrapped heading or a stray
# measurement, and they dominate the data (379 of them across test-data/
# against 160 three-line runs).
#
# SUBSTANTIAL_RUN_LINES marks the runs worth pointing a reader at. Block
# quotations in the sample run 3-8 lines; the histogram thins sharply above
# 10 (11 runs of exactly 10 lines, then 6 runs in total across 11-32 lines).
# A run at or above this length is longer than a typical quotation, so it is
# named with its page. Below it, runs are counted but not located.
MIN_REPORTABLE_RUN_LINES = 3
SUBSTANTIAL_RUN_LINES = 8

# --- Page limits ---
PAGE_LIMITS = {
    BriefType.APPELLANT: 38,
    BriefType.APPELLEE: 38,
    BriefType.CROSS_APPEAL: 38,
    BriefType.REPLY: 12,
    BriefType.AMICUS: 19,
    BriefType.AMICUS_REHEARING: 10,
    BriefType.PETITION_REHEARING: 10,
}

# --- Cover color by brief type ---
# Rule 32(a)(2): colors for brief covers
COVER_COLORS = {
    BriefType.APPELLANT: "blue",
    BriefType.APPELLEE: "red",
    BriefType.REPLY: "gray",
    BriefType.CROSS_APPEAL: "gray",
    BriefType.AMICUS: "green",
    BriefType.AMICUS_REHEARING: "green",
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
