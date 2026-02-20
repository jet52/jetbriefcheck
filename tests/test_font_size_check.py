"""Tests for the enhanced FMT-006 per-page font size check.

Covers:
- All compliant pages → PASS
- Noncompliant body text on a page → REJECT with per-page detail
- Noncompliant characters only in header/footer zone → category breakdown
- Noncompliant superscript spans → category breakdown
- Severity downgrade to NOTE when all pages have < threshold noncompliant chars
- Multiple pages with mixed categories
- Edge cases: empty pages, no fonts, single span
- Small-caps heuristic detection (Layer 1)
- Location-aware weighting for small caps (Layer 2)
- Graduated severity: PASS with note when all chars are harmless (Layer 3)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from core.constants import FONT_NONCOMPLIANT_THRESHOLD, FONT_SIZE_TOLERANCE, MIN_FONT_SIZE_PT
from core.checks_mechanical import (
    _check_font_size_per_page,
    _classify_font_span,
    _is_all_uppercase,
)
from core.models import BriefMetadata, PageInfo, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_font(size: float, chars: int = 20, origin_y: float = 400.0,
               flags: int = 0, name: str = "TimesNewRoman",
               text: str = "") -> dict:
    return {"name": name, "size": size, "flags": flags,
            "chars": chars, "origin_y": origin_y, "text": text}


def _make_page(page_number: int, fonts: list[dict],
               height_inches: float = 11.0, text: str = "") -> PageInfo:
    return PageInfo(
        page_number=page_number,
        width_inches=8.5,
        height_inches=height_inches,
        left_margin_inches=1.5,
        right_margin_inches=1.0,
        top_margin_inches=1.0,
        bottom_margin_inches=1.0,
        fonts=fonts,
        text=text,
    )


def _make_metadata(pages: list[PageInfo],
                   predominant_font_size: float = 12.0) -> BriefMetadata:
    all_sizes = [f["size"] for p in pages for f in p.fonts if f["size"] > 0]
    return BriefMetadata(
        pages=pages,
        min_font_size=min(all_sizes) if all_sizes else None,
        predominant_font_size=predominant_font_size,
    )


# ---------------------------------------------------------------------------
# _classify_font_span tests
# ---------------------------------------------------------------------------

class TestClassifyFontSpan:
    """Unit tests for the span classification helper."""

    def test_body_text(self):
        font = _make_font(size=10.0, origin_y=400.0, chars=30)
        assert _classify_font_span(font, 792.0) == "body"

    def test_top_header_zone(self):
        # origin_y at 50pt on an 11-inch (792pt) page → 6.3% from top
        font = _make_font(size=10.0, origin_y=50.0, chars=30)
        assert _classify_font_span(font, 792.0) == "header_footer"

    def test_bottom_footer_zone(self):
        # origin_y at 750pt on 792pt page → 94.7% from top
        font = _make_font(size=10.0, origin_y=750.0, chars=30)
        assert _classify_font_span(font, 792.0) == "header_footer"

    def test_superscript_flag(self):
        # bit 0 set → superscript, even if in body zone
        font = _make_font(size=8.0, origin_y=400.0, chars=2, flags=1)
        assert _classify_font_span(font, 792.0) == "superscript"

    def test_short_digit_text_as_superscript(self):
        # <=4 chars, small size, no superscript flag → still superscript
        font = _make_font(size=8.0, origin_y=400.0, chars=2, flags=0)
        assert _classify_font_span(font, 792.0) == "superscript"

    def test_short_text_compliant_size_is_body(self):
        # <=4 chars but size is compliant → doesn't trigger superscript path
        # (won't be called for compliant spans in practice, but test the logic)
        font = _make_font(size=12.0, origin_y=400.0, chars=2, flags=0)
        assert _classify_font_span(font, 792.0) == "body"

    def test_header_footer_takes_priority_over_superscript(self):
        # In footer zone AND superscript flag set → header_footer wins
        font = _make_font(size=8.0, origin_y=760.0, chars=2, flags=1)
        assert _classify_font_span(font, 792.0) == "header_footer"

    def test_boundary_top_zone(self):
        # Exactly at 10% boundary
        font = _make_font(size=10.0, origin_y=79.2, chars=10)
        assert _classify_font_span(font, 792.0) == "header_footer"

    def test_just_inside_body_from_top(self):
        # Just past 10% boundary
        font = _make_font(size=10.0, origin_y=80.0, chars=10)
        # 80 > 79.2 and 80 < 712.8 → body (but small size + <=4 chars check)
        # chars=10, so not caught by short-text rule → body
        assert _classify_font_span(font, 792.0) == "body"


# ---------------------------------------------------------------------------
# _check_font_size_per_page tests
# ---------------------------------------------------------------------------

class TestFontSizePerPage:
    """Integration tests for the FMT-006 per-page check."""

    def test_all_compliant_passes(self):
        pages = [
            _make_page(0, [_make_font(12.0, chars=500)]),
            _make_page(1, [_make_font(12.5, chars=800)]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True
        assert result.check_id == "FMT-006"
        assert result.severity == Severity.REJECT

    def test_font_at_tolerance_boundary_passes(self):
        # 12.0 - 0.3 = 11.7; font at exactly 11.7 should pass
        pages = [_make_page(0, [_make_font(11.7, chars=500)])]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True

    def test_font_just_below_tolerance_fails(self):
        pages = [_make_page(0, [_make_font(11.6, chars=500)])]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is False

    def test_noncompliant_body_text_reject(self):
        """>=10 noncompliant body chars on a page → REJECT severity."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=15, origin_y=400.0),  # body, nc
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is False
        assert result.severity == Severity.REJECT
        assert "page 1" in result.message
        assert "15 of 515 chars" in result.details
        assert "15 body" in result.details

    def test_few_noncompliant_chars_note_severity(self):
        """<10 noncompliant chars on every page → NOTE severity."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=5, origin_y=400.0),  # body, nc but <10
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is False
        assert result.severity == Severity.NOTE
        assert "page 1" in result.message

    def test_header_footer_categorised(self):
        """Noncompliant chars only in footer zone → PASS with note."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                # Footer zone: origin_y=750 on 11-inch (792pt) page
                _make_font(10.0, chars=3, origin_y=750.0),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True
        assert "headers/footers" in result.details

    def test_header_footer_plus_body_shows_both(self):
        """Noncompliant chars in footer + body → FAIL with header/footer label."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=3, origin_y=750.0),     # footer
                _make_font(10.0, chars=15, origin_y=400.0),    # body
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is False
        assert "header/footer" in result.details
        assert "body" in result.details

    def test_superscript_categorised(self):
        """Noncompliant chars only superscript → PASS with note."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(8.0, chars=2, origin_y=400.0, flags=1),  # superscript
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True
        assert "superscripts" in result.details

    def test_short_digit_text_as_superscript(self):
        """Short small-font text (<=4 chars, no flag) → superscript → PASS."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(9.0, chars=3, origin_y=400.0, flags=0),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True
        assert "superscripts" in result.details

    def test_mixed_categories_on_one_page(self):
        """Body + header/footer + superscript all on one page."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=800, origin_y=400.0),
                _make_font(10.0, chars=20, origin_y=400.0),   # body
                _make_font(10.0, chars=5, origin_y=750.0),     # footer
                _make_font(8.0, chars=2, origin_y=400.0, flags=1),  # superscript
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is False
        assert result.severity == Severity.REJECT  # 27 total >= 10
        assert "20 body" in result.details
        assert "5 header/footer" in result.details
        assert "2 superscript" in result.details
        assert "27 of 827 chars" in result.details

    def test_multiple_pages_mixed(self):
        """Two pages: one serious, one minor."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=50, origin_y=400.0),   # 50 body nc → REJECT
            ]),
            _make_page(1, [
                _make_font(12.0, chars=600, origin_y=400.0),
                _make_font(10.0, chars=3, origin_y=750.0),    # 3 footer nc
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is False
        assert result.severity == Severity.REJECT  # page 0 has 50 >= 10
        assert "Page 1" in result.details
        assert "Page 2" in result.details

    def test_multiple_pages_all_harmless_pass(self):
        """All noncompliant chars are header/footer or superscript → PASS."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=3, origin_y=750.0),       # header/footer
            ]),
            _make_page(1, [
                _make_font(12.0, chars=600, origin_y=400.0),
                _make_font(9.0, chars=2, origin_y=400.0, flags=1),  # superscript
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True
        assert "headers/footers" in result.details
        assert "superscripts" in result.details

    def test_page_with_no_fonts_skipped(self):
        pages = [
            _make_page(0, []),
            _make_page(1, [_make_font(12.0, chars=200)]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.passed is True

    def test_empty_pages_list(self):
        result = _check_font_size_per_page(_make_metadata([]))
        assert result.passed is True

    def test_percentage_in_details(self):
        """Details string includes noncompliant percentage."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=90, origin_y=400.0),
                _make_font(10.0, chars=10, origin_y=400.0),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert "10.0%" in result.details

    def test_global_min_size_in_message(self):
        """Message reports the smallest font size found globally."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500),
                _make_font(9.5, chars=15, origin_y=400.0),
            ]),
            _make_page(1, [
                _make_font(12.0, chars=500),
                _make_font(10.5, chars=15, origin_y=400.0),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert "9.5pt" in result.message

    def test_predominant_size_in_details(self):
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500),
                _make_font(10.0, chars=15, origin_y=400.0),
            ]),
        ]
        meta = _make_metadata(pages, predominant_font_size=12.0)
        result = _check_font_size_per_page(meta)
        assert "Predominant font size: 12.0pt" in result.details

    def test_exactly_threshold_count_is_reject(self):
        """Exactly FONT_NONCOMPLIANT_THRESHOLD chars → REJECT."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=FONT_NONCOMPLIANT_THRESHOLD, origin_y=400.0),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.severity == Severity.REJECT

    def test_one_below_threshold_is_note(self):
        """FONT_NONCOMPLIANT_THRESHOLD - 1 chars → NOTE."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=FONT_NONCOMPLIANT_THRESHOLD - 1, origin_y=400.0),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages))
        assert result.severity == Severity.NOTE


# ---------------------------------------------------------------------------
# _is_all_uppercase tests
# ---------------------------------------------------------------------------

class TestIsAllUppercase:
    """Unit tests for the small-caps uppercase heuristic helper."""

    def test_all_uppercase(self):
        assert _is_all_uppercase("SMITH") is True

    def test_mixed_case(self):
        assert _is_all_uppercase("Smith") is False

    def test_all_lowercase(self):
        assert _is_all_uppercase("smith") is False

    def test_uppercase_with_punctuation(self):
        assert _is_all_uppercase("V.") is True
        assert _is_all_uppercase("SMITH,") is True

    def test_uppercase_with_spaces(self):
        assert _is_all_uppercase("IN RE") is True

    def test_digits_only(self):
        # No alpha chars → not small caps
        assert _is_all_uppercase("123") is False

    def test_empty_string(self):
        assert _is_all_uppercase("") is False

    def test_punctuation_only(self):
        assert _is_all_uppercase("...") is False

    def test_single_uppercase_letter(self):
        assert _is_all_uppercase("D.") is True

    def test_unicode_uppercase(self):
        assert _is_all_uppercase("ÉTAT") is True


# ---------------------------------------------------------------------------
# Small-caps classification tests (Layer 1)
# ---------------------------------------------------------------------------

class TestSmallCapsClassification:
    """Tests for the small-caps heuristic in _classify_font_span."""

    def test_all_uppercase_at_sc_ratio(self):
        """All-uppercase text at 65% of body font → small_caps."""
        # 13pt body font, 8.5pt span → ratio ~0.654
        font = _make_font(size=8.5, origin_y=400.0, chars=10, text="STATEMENT")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "small_caps"

    def test_mixed_case_not_small_caps(self):
        """Mixed-case text → body (not small_caps), even at correct ratio."""
        font = _make_font(size=8.5, origin_y=400.0, chars=10, text="Statement")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "body"

    def test_ratio_too_low(self):
        """Uppercase text but ratio below 0.55 → body."""
        # 13pt body, 6pt span → ratio ~0.46
        font = _make_font(size=6.0, origin_y=400.0, chars=10, text="ABC")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "body"

    def test_ratio_too_high(self):
        """Uppercase text but ratio above 0.85 → body."""
        # 12pt body, 11pt span → ratio ~0.917
        font = _make_font(size=11.0, origin_y=400.0, chars=10, text="ABC")
        assert _classify_font_span(font, 792.0, predominant_size=12.0) == "body"

    def test_ratio_at_lower_bound(self):
        """Ratio exactly at 0.55 → small_caps."""
        # 20pt body, 11pt span → ratio 0.55
        font = _make_font(size=11.0, origin_y=400.0, chars=10, text="ABC")
        assert _classify_font_span(font, 792.0, predominant_size=20.0) == "small_caps"

    def test_ratio_at_upper_bound(self):
        """Ratio exactly at 0.85 → small_caps."""
        # 10pt body, 8.5pt span → ratio 0.85
        font = _make_font(size=8.5, origin_y=400.0, chars=10, text="ABC")
        assert _classify_font_span(font, 792.0, predominant_size=10.0) == "small_caps"

    def test_no_predominant_size_falls_back_to_body(self):
        """Without predominant size, cannot detect small caps → body."""
        font = _make_font(size=8.5, origin_y=400.0, chars=10, text="STATEMENT")
        assert _classify_font_span(font, 792.0) == "body"

    def test_no_text_falls_back_to_body(self):
        """Without text content, cannot detect small caps → body."""
        font = _make_font(size=8.5, origin_y=400.0, chars=10)
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "body"

    def test_header_footer_takes_priority_over_small_caps(self):
        """Small caps in footer zone → header_footer (not small_caps)."""
        font = _make_font(size=8.5, origin_y=750.0, chars=10, text="COURT")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "header_footer"

    def test_superscript_takes_priority_over_small_caps(self):
        """Small-caps-like text with superscript flag → superscript."""
        font = _make_font(size=8.0, origin_y=400.0, chars=2, flags=1, text="ST")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "superscript"

    def test_short_chars_superscript_over_small_caps(self):
        """<=4 chars at small size → superscript, even if all uppercase."""
        font = _make_font(size=8.0, origin_y=400.0, chars=2, text="ND")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "superscript"

    def test_case_citation_pattern(self):
        """'V.' at small-caps size → small_caps."""
        font = _make_font(size=8.5, origin_y=400.0, chars=5, text="V.")
        # chars=5 > 4 so not caught by short-text superscript
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "small_caps"

    def test_digits_not_small_caps(self):
        """Pure digit text at SC ratio → body (not small_caps)."""
        font = _make_font(size=8.5, origin_y=400.0, chars=10, text="2023")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "body"

    def test_typical_cover_court_name(self):
        """Court name like 'SUPREME COURT' at SC ratio → small_caps."""
        font = _make_font(size=8.5, origin_y=400.0, chars=13, text="SUPREME COURT")
        assert _classify_font_span(font, 792.0, predominant_size=13.0) == "small_caps"


# ---------------------------------------------------------------------------
# Small-caps integration tests (Layers 2 & 3)
# ---------------------------------------------------------------------------

class TestSmallCapsIntegration:
    """Integration tests for small-caps in the full FMT-006 check."""

    def test_small_caps_only_on_cover_pass(self):
        """Small caps on cover page (page 0) → PASS with informational note."""
        pages = [
            _make_page(0, [
                _make_font(13.0, chars=200, origin_y=400.0),
                _make_font(8.5, chars=30, origin_y=400.0, text="SUPREME COURT"),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is True
        assert "small caps" in result.details.lower()

    def test_small_caps_on_certificate_page_pass(self):
        """Small caps on a page with 'Certificate of Service' → PASS."""
        pages = [
            _make_page(5, [
                _make_font(13.0, chars=300, origin_y=400.0),
                _make_font(8.5, chars=20, origin_y=400.0, text="JOHN SMITH"),
            ], text="Certificate of Service\nI hereby certify..."),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is True
        assert "small caps" in result.details.lower()

    def test_small_caps_on_toa_page_pass(self):
        """Small caps on a Table of Authorities page → PASS."""
        pages = [
            _make_page(3, [
                _make_font(13.0, chars=500, origin_y=400.0),
                _make_font(8.5, chars=40, origin_y=400.0, text="SMITH V. JONES"),
            ], text="Table of Authorities\nCases\nSmith v. Jones..."),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is True

    def test_small_caps_moderate_on_body_page_pass(self):
        """Small caps under the suspicious threshold on a body page → PASS."""
        # 50 small-caps chars out of 5050 total = ~1% → under 15%
        pages = [
            _make_page(5, [
                _make_font(13.0, chars=5000, origin_y=400.0),
                _make_font(8.5, chars=50, origin_y=400.0, text="SMITH V. JONES"),
            ], text="Argument\nThe defendant argues..."),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is True

    def test_excessive_small_caps_on_body_page_reclassified(self):
        """Small caps > 15% of a non-conventional page → reclassified as body."""
        # 200 small-caps chars out of 1000 total = 20% → above 15% threshold
        pages = [
            _make_page(5, [
                _make_font(13.0, chars=800, origin_y=400.0),
                _make_font(8.5, chars=200, origin_y=400.0, text="ENTIRE PARAGRAPH IN SMALL CAPS"),
            ], text="Argument\nThe defendant argues..."),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is False
        assert result.severity == Severity.REJECT  # 200 >= 10 → REJECT
        assert "200 body" in result.details

    def test_excessive_small_caps_on_conventional_page_stays_small_caps(self):
        """Large amount of small caps on cover page → still benign."""
        # Cover page is always conventional
        pages = [
            _make_page(0, [
                _make_font(13.0, chars=100, origin_y=400.0),
                _make_font(8.5, chars=200, origin_y=400.0, text="SUPREME COURT OF NORTH DAKOTA"),
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is True

    def test_small_caps_mixed_with_body_violations(self):
        """Small caps + genuine body violations → FAIL, small caps noted."""
        pages = [
            _make_page(0, [
                _make_font(13.0, chars=500, origin_y=400.0),
                _make_font(8.5, chars=20, origin_y=400.0, text="COURT NAME"),  # small caps
            ]),
            _make_page(3, [
                _make_font(13.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=50, origin_y=400.0),  # body (no text → body)
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is False
        assert result.severity == Severity.REJECT  # 50 body >= 10
        assert "small caps" in result.details.lower()
        assert "50 body" in result.details

    def test_small_caps_details_mention_pages(self):
        """PASS details mention which pages have small caps."""
        pages = [
            _make_page(0, [
                _make_font(13.0, chars=300, origin_y=400.0),
                _make_font(8.5, chars=15, origin_y=400.0, text="SUPREME COURT"),
            ]),
            _make_page(4, [
                _make_font(13.0, chars=500, origin_y=400.0),
                _make_font(8.5, chars=10, origin_y=400.0, text="SMITH V. JONES"),
            ], text="Table of Authorities\nCases..."),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is True
        assert "small caps" in result.details.lower()

    def test_body_violations_severity_uses_body_count_only(self):
        """Severity is based on nc_body, not nc_total (small caps excluded)."""
        # nc_small_caps=50 but nc_body=5 — should be NOTE, not REJECT
        pages = [
            _make_page(0, [
                _make_font(13.0, chars=5000, origin_y=400.0),
                _make_font(8.5, chars=50, origin_y=400.0, text="COURT NAME HERE"),  # SC
                _make_font(10.0, chars=5, origin_y=400.0),   # body, < threshold
            ]),
        ]
        result = _check_font_size_per_page(_make_metadata(pages, predominant_font_size=13.0))
        assert result.passed is False
        assert result.severity == Severity.NOTE  # 5 body < 10 threshold

    def test_backward_compat_no_text_no_predominant(self):
        """Fonts without text/predominant_size work as before (body classification)."""
        pages = [
            _make_page(0, [
                _make_font(12.0, chars=500, origin_y=400.0),
                _make_font(10.0, chars=15, origin_y=400.0),  # no text → body
            ]),
        ]
        meta = _make_metadata(pages, predominant_font_size=None)
        result = _check_font_size_per_page(meta)
        assert result.passed is False
        assert result.severity == Severity.REJECT
        assert "15 body" in result.details
