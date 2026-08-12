"""Tests for page-number recognition and its effect on margin measurement.

Rule 32(a)(4) requires 1" margins and requires pages to be numbered at the
bottom, but is silent on where the number may sit.  The checker therefore
excludes page-number footers (and only those) from the bottom margin.

Two block classes must be excluded from the measured text area:

* page-number footers in the bottom zone — otherwise a properly numbered
  brief reports a short bottom margin (FMT-005);
* blocks with no extractable text — scanned and re-imaged PDFs carry empty
  text objects that occupy space but show no ink.

The same recognizer drives ``_detect_page_number`` (FMT-011 / FMT-012), so a
footer counts as a page number for the margin calculation and the numbering
checks alike, or for neither.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

import fitz  # PyMuPDF

from core.pdf_extract import (
    _block_text,
    _compute_margins,
    _detect_page_number,
    _page_number_value,
)


PAGE_W = 612.0   # 8.5" at 72 dpi
PAGE_H = 792.0   # 11"  at 72 dpi
BOTTOM_ZONE = PAGE_H * 0.9  # 712.8 — blocks at/below this are footer candidates


def _rect() -> fitz.Rect:
    return fitz.Rect(0, 0, PAGE_W, PAGE_H)


def _block(text: str, bbox: tuple[float, float, float, float]) -> dict:
    """Build a minimal MuPDF text block carrying *text* at *bbox*."""
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{"spans": [{"text": text, "bbox": bbox}]}],
    }


def _body_block() -> dict:
    """A block of body text inside the 1" margins (72 pt from each edge)."""
    return _block("Body text of the brief.", (108.0, 72.0, 504.0, 600.0))


# ===================================================================
# _page_number_value
# ===================================================================

class TestPageNumberValue:
    """The shared recognizer: what counts as a page-number footer."""

    @pytest.mark.parametrize("text,expected", [
        # Bare arabic, with the decorations filers actually use
        ("5", "5"),
        ("-5-", "5"),
        ("- 5 -", "5"),
        ("– 5 –", "5"),        # en dash
        ("— 5 —", "5"),        # em dash
        ("[5]", "5"),
        ("(5)", "5"),
        ("12", "12"),
        # Roman numerals (front matter)
        ("iv", "iv"),
        ("-iv-", "iv"),
        ("IV", "IV"),
        # Labeled forms
        ("Page 5", "5"),
        ("page 5", "5"),
        ("Page 5 of 25", "5"),
        ("PAGE 5 OF 25", "5"),
        ("5 of 25", "5"),
        ("Page ii of 25", "ii"),
    ])
    def test_recognized(self, text, expected):
        assert _page_number_value(text) == expected

    @pytest.mark.parametrize("text", [
        "",
        "   ",
        "Smith v. Jones",
        "No. 20990002",
        "Page 5 of the transcript",   # labeled but carries prose
        "Brief of Appellant",
        "See R156:12",
        "5 U.S.C. 552",
        "Appendix 5",
    ])
    def test_not_recognized(self, text):
        """Anything carrying content beyond the number is content."""
        assert _page_number_value(text) is None

    def test_returns_bare_numeral_for_decorated_footer(self):
        """The numeral is returned, not the raw footer — FMT-012 compares it."""
        assert _page_number_value("Page 1 of 25") == "1"
        assert _page_number_value("- 1 -") == "1"


# ===================================================================
# _block_text
# ===================================================================

class TestBlockText:

    def test_concatenates_spans(self):
        block = {
            "type": 0,
            "bbox": (0, 0, 100, 100),
            "lines": [
                {"spans": [{"text": "Page "}, {"text": "5"}]},
                {"spans": [{"text": " of 25"}]},
            ],
        }
        assert _block_text(block) == "Page 5 of 25"

    def test_empty_block_returns_empty_string(self):
        assert _block_text({"type": 0, "bbox": (0, 0, 10, 10), "lines": []}) == ""

    def test_whitespace_only_block_returns_empty_string(self):
        assert _block_text(_block("   \n  ", (0, 0, 10, 10))) == ""


# ===================================================================
# _compute_margins
# ===================================================================

class TestComputeMargins:

    def test_page_number_footer_excluded_from_bottom_margin(self):
        """A bare page number below the margin does not shorten it."""
        blocks = [_body_block(), _block("5", (300.0, 740.0, 312.0, 752.0))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        # Body text ends at 600; footer at 752 is ignored
        assert bottom == pytest.approx((PAGE_H - 600.0) / 72.0, abs=0.01)

    def test_page_of_footer_excluded_from_bottom_margin(self):
        """'Page N of M' is a page number too — the FMT-005 regression."""
        blocks = [_body_block(), _block("Page 5 of 25", (270.0, 740.0, 342.0, 752.0))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom == pytest.approx((PAGE_H - 600.0) / 72.0, abs=0.01)
        assert bottom >= 1.0

    def test_roman_page_of_footer_excluded(self):
        """'Page ii of 25' — labeled roman front-matter numbering."""
        blocks = [_body_block(), _block("Page ii of 25", (270.0, 740.0, 342.0, 752.0))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom >= 1.0

    def test_non_page_number_footer_still_counts(self):
        """A footer carrying real content is content and shortens the margin."""
        blocks = [_body_block(), _block("Brief of Appellant", (108.0, 740.0, 300.0, 752.0))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom == pytest.approx((PAGE_H - 752.0) / 72.0, abs=0.01)
        assert bottom < 1.0

    def test_empty_block_in_bottom_zone_excluded(self):
        """Invisible text objects define no margin — the second regression."""
        blocks = [_body_block(), _block("", (108.0, 718.9, 504.0, 732.2))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom == pytest.approx((PAGE_H - 600.0) / 72.0, abs=0.01)
        assert bottom >= 1.0

    def test_empty_block_outside_bottom_zone_also_excluded(self):
        """An empty block anywhere defines no margin, not just in the footer."""
        # An empty block hugging the left edge must not shrink the left margin
        blocks = [_body_block(), _block("   ", (10.0, 300.0, 40.0, 320.0))]
        left, _, _, _ = _compute_margins(blocks, _rect())
        assert left == pytest.approx(108.0 / 72.0, abs=0.01)

    def test_page_number_above_bottom_zone_counts_as_content(self):
        """The exclusion is footer-only; a stray numeral mid-page is content."""
        blocks = [_body_block(), _block("5", (108.0, 650.0, 120.0, 662.0))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom == pytest.approx((PAGE_H - 662.0) / 72.0, abs=0.01)

    def test_image_blocks_ignored(self):
        blocks = [_body_block(), {"type": 1, "bbox": (0.0, 700.0, 612.0, 792.0)}]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom == pytest.approx((PAGE_H - 600.0) / 72.0, abs=0.01)

    def test_no_blocks_returns_full_page(self):
        left, right, top, bottom = _compute_margins([], _rect())
        assert top == pytest.approx(PAGE_H / 72.0)
        assert bottom == pytest.approx(PAGE_H / 72.0)

    def test_only_excluded_blocks_returns_full_page(self):
        """A page of nothing but empty blocks has no measurable text area."""
        blocks = [_block("", (108.0, 718.9, 504.0, 732.2))]
        left, right, top, bottom = _compute_margins(blocks, _rect())
        assert top == pytest.approx(PAGE_H / 72.0)


# ===================================================================
# _detect_page_number
# ===================================================================

class TestDetectPageNumber:

    def test_detects_bare_numeral(self):
        blocks = [_body_block(), _block("5", (300.0, 740.0, 312.0, 752.0))]
        found, value, unknown = _detect_page_number(blocks, _rect(), "", 4)
        assert found is True
        assert value == "5"
        assert unknown is False

    def test_detects_page_of_form(self):
        """FMT-011 regression: 'Page 1 of 25' is a page number."""
        blocks = [_body_block(), _block("Page 1 of 25", (270.0, 740.0, 342.0, 752.0))]
        found, value, _ = _detect_page_number(blocks, _rect(), "", 0)
        assert found is True
        # Normalized to the bare numeral so FMT-012's == "1" comparison works
        assert value == "1"

    def test_roman_cover_number_reported_as_roman(self):
        """FMT-012 must still catch front matter that starts at 'i', not '1'."""
        blocks = [_body_block(), _block("Page i of 25", (270.0, 740.0, 342.0, 752.0))]
        found, value, _ = _detect_page_number(blocks, _rect(), "", 0)
        assert found is True
        assert value == "i"
        assert value != "1"

    def test_no_footer_returns_false(self):
        found, value, unknown = _detect_page_number([_body_block()], _rect(), "", 3)
        assert found is False
        assert value is None
        assert unknown is False, "a page with a clear footer area is not indeterminate"

    def test_content_footer_is_not_a_page_number(self):
        blocks = [_body_block(), _block("Brief of Appellant", (108.0, 740.0, 300.0, 752.0))]
        found, value, _ = _detect_page_number(blocks, _rect(), "", 3)
        assert found is False

    def test_agrees_with_margin_exclusion(self):
        """A footer that is only a page number counts for both purposes."""
        for footer in ("5", "-5-", "Page 5 of 25", "Page ii of 25", "[5]", "pg. 5"):
            blocks = [_body_block(), _block(footer, (270.0, 740.0, 342.0, 752.0))]
            found, _, _ = _detect_page_number(blocks, _rect(), "", 4)
            _, _, _, bottom = _compute_margins(blocks, _rect())
            assert found is True, f"{footer!r} not detected as a page number"
            assert bottom >= 1.0, f"{footer!r} counted against the bottom margin"

        for footer in ("Brief of Appellant", "No. 20990002"):
            blocks = [_body_block(), _block(footer, (108.0, 740.0, 342.0, 752.0))]
            found, _, _ = _detect_page_number(blocks, _rect(), "", 4)
            _, _, _, bottom = _compute_margins(blocks, _rect())
            assert found is False, f"{footer!r} wrongly detected as a page number"
            assert bottom < 1.0, f"{footer!r} wrongly excluded from the margin"


# ===================================================================
# Detection zone — reaches higher than the margin zone
# ===================================================================

class TestPageNumberZone:
    """Detection covers the bottom 15%; margin exclusion only the bottom 10%.

    Rule 32(a)(4) requires numbering "at the bottom" without saying how far
    up that reaches. Filers routinely set the number at 87-89% of page
    height — clear of the 1" margin, but above the margin zone. Holding
    detection to the margin zone reported 150 pages in test-data/ as
    unnumbered when the number was plainly printed.
    """

    # 87.3% of 792 = 691.4 — where the sample briefs put it
    ABOVE_MARGIN_ZONE = (300.0, 691.4, 312.0, 703.0)

    def test_number_above_margin_zone_is_detected(self):
        blocks = [_body_block(), _block("5", self.ABOVE_MARGIN_ZONE)]
        found, value, _ = _detect_page_number(blocks, _rect(), "", 4)
        assert found is True
        assert value == "5"

    def test_number_above_margin_zone_still_counts_toward_margin(self):
        """Detection reaching higher must not widen the margin exclusion.

        A block at 87% sits inside the text area, not the bottom margin, so
        it is ordinary content for measurement purposes.
        """
        blocks = [_block("5", self.ABOVE_MARGIN_ZONE)]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom == pytest.approx((PAGE_H - 703.0) / 72.0, abs=0.01)

    def test_number_above_the_detection_zone_not_detected(self):
        """Mid-page numerals are not page numbers."""
        blocks = [_body_block(), _block("5", (108.0, 400.0, 120.0, 412.0))]
        found, _, _ = _detect_page_number(blocks, _rect(), "", 4)
        assert found is False


# ===================================================================
# Indeterminate footers
# ===================================================================

class TestIndeterminateFooter:
    """"Cannot read the footer" must not be reported as "not numbered"."""

    def test_empty_footer_block_is_indeterminate(self):
        blocks = [_body_block(), _block("", (108.0, 718.9, 504.0, 732.2))]
        found, value, unknown = _detect_page_number(blocks, _rect(), "", 4)
        assert found is False
        assert value is None
        assert unknown is True

    def test_image_in_footer_zone_is_indeterminate(self):
        """Scanned briefs carry the number in the page image."""
        blocks = [_body_block(), {"type": 1, "bbox": (0.0, 700.0, 612.0, 780.0)}]
        found, _, unknown = _detect_page_number(blocks, _rect(), "", 4)
        assert found is False
        assert unknown is True

    def test_readable_number_beats_unreadable_block(self):
        """An empty block alongside a legible number is not indeterminate."""
        blocks = [
            _body_block(),
            _block("", (108.0, 718.9, 200.0, 732.2)),
            _block("5", (300.0, 740.0, 312.0, 752.0)),
        ]
        found, value, unknown = _detect_page_number(blocks, _rect(), "", 4)
        assert found is True
        assert value == "5"
        assert unknown is False

    def test_image_outside_footer_zone_is_not_indeterminate(self):
        """A figure mid-page says nothing about the footer."""
        blocks = [_body_block(), {"type": 1, "bbox": (100.0, 200.0, 500.0, 400.0)}]
        found, _, unknown = _detect_page_number(blocks, _rect(), "", 4)
        assert found is False
        assert unknown is False


# ===================================================================
# Running footers that begin with a page number
# ===================================================================

class TestRunningFooter:
    """A footer may merge the number with a title in one block.

    Such a page IS numbered (FMT-011), but the block is not purely a page
    number, so it still counts against the bottom margin (FMT-005).
    """

    FOOTER = "Page 1 of 2 Brief in Support of Motion for Extension of Time"

    def test_detected_as_numbered(self):
        blocks = [_body_block(), _block(self.FOOTER, (108.0, 740.0, 504.0, 752.0))]
        found, value, _ = _detect_page_number(blocks, _rect(), "", 0)
        assert found is True
        assert value == "1"

    def test_still_counts_against_the_margin(self):
        blocks = [_body_block(), _block(self.FOOTER, (108.0, 740.0, 504.0, 752.0))]
        _, _, _, bottom = _compute_margins(blocks, _rect())
        assert bottom < 1.0

    def test_prose_beginning_with_a_number_is_not_a_footer(self):
        """The page-number label is required — a bare leading numeral is not."""
        blocks = [_body_block(),
                  _block("5 witnesses testified at the hearing below",
                         (108.0, 740.0, 504.0, 752.0))]
        found, _, _ = _detect_page_number(blocks, _rect(), "", 4)
        assert found is False
