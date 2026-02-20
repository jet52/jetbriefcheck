"""Tests for line-spacing detection and the FMT-009 double-spacing check.

Covers:
- Unit tests for ``_estimate_line_spacing`` with synthetic MuPDF block dicts
- Integration tests with programmatically-generated PDFs at standard spacings
  (MS Word single / 1.15 / 1.5 / double and Adobe auto / double)
- FMT-009 compliance check (``_check_double_spacing``) with synthetic metadata
- Edge cases: empty blocks, mixed spacing, single-line blocks, footnote zones

MS Word / Adobe line-spacing reference values (12 pt body text):
    Single (MS Word)  ≈ 14.4 pt  (font_size × 1.2)
    1.15   (Word default) ≈ 16.6 pt  (font_size × 1.38)
    1.5 lines         ≈ 21.6 pt  (font_size × 1.8)
    Double (MS Word)  ≈ 28.8 pt  (font_size × 2.4, i.e. 2 × single)
    Adobe auto        ≈ 14.4 pt  (120 % of font_size)
    Adobe double      ≈ 24.0 pt  (200 % of font_size, i.e. "Exactly 24 pt")
"""

from __future__ import annotations

import statistics
import sys
import tempfile
from pathlib import Path
from typing import Optional

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import fitz  # PyMuPDF

from core.constants import MIN_DOUBLE_SPACE_PTS
from core.checks_mechanical import _check_double_spacing
from core.models import BriefMetadata, PageInfo, Severity
from core.pdf_extract import _estimate_line_spacing


# ---------------------------------------------------------------------------
# MS Word / Adobe standard spacing values (pts) for 12 pt text
# ---------------------------------------------------------------------------

FONT_SIZE_12 = 12.0

# MS Word: single = font × 1.2 (OS/2 table default for most fonts)
MS_WORD_SINGLE_12PT = 14.4
# MS Word default "single" since Word 2007 is really 1.15×
MS_WORD_115_12PT = 16.56
# MS Word 1.5 lines
MS_WORD_150_12PT = 21.6
# MS Word double = 2 × single
MS_WORD_DOUBLE_12PT = 28.8
# Adobe InDesign auto leading = 120% of font size
ADOBE_AUTO_12PT = 14.4
# Adobe "double" = exactly 2× font size
ADOBE_DOUBLE_12PT = 24.0

# For 10 pt text
FONT_SIZE_10 = 10.0
MS_WORD_SINGLE_10PT = 12.0
MS_WORD_DOUBLE_10PT = 24.0
ADOBE_AUTO_10PT = 12.0


# ---------------------------------------------------------------------------
# Helpers – synthetic MuPDF block dicts
# ---------------------------------------------------------------------------

def _make_span(text: str, origin_y: float, font_size: float = 12.0) -> dict:
    """Build a minimal MuPDF span dict."""
    return {
        "text": text,
        "origin": (108.0, origin_y),
        "font": "Helvetica",
        "size": font_size,
        "flags": 0,
        "color": 0,
        "bbox": (108.0, origin_y - font_size, 400.0, origin_y),
    }


def _make_line(origin_y: float, text: str = "Sample text", font_size: float = 12.0) -> dict:
    """Build a minimal MuPDF line dict."""
    span = _make_span(text, origin_y, font_size)
    return {
        "spans": [span],
        "bbox": span["bbox"],
        "wmode": 0,
        "dir": (1.0, 0.0),
    }


def _make_block(origin_ys: list[float], font_size: float = 12.0) -> dict:
    """Build a text block with lines at the given baseline y-positions."""
    lines = [_make_line(y, f"Line at y={y}", font_size) for y in origin_ys]
    top = min(y - font_size for y in origin_ys)
    bottom = max(origin_ys)
    return {
        "type": 0,
        "bbox": (108.0, top, 400.0, bottom),
        "lines": lines,
    }


def _make_image_block() -> dict:
    """Build an image block (type 1) — should be skipped."""
    return {"type": 1, "bbox": (0, 0, 100, 100)}


# ---------------------------------------------------------------------------
# Helpers – PageInfo / BriefMetadata
# ---------------------------------------------------------------------------

def _make_page(page_number: int, line_spacing: Optional[float] = None) -> PageInfo:
    return PageInfo(
        page_number=page_number,
        width_inches=8.5,
        height_inches=11.0,
        left_margin_inches=1.5,
        right_margin_inches=1.0,
        top_margin_inches=1.0,
        bottom_margin_inches=1.0,
        line_spacing=line_spacing,
        text="Body text." if page_number > 0 else "Cover page",
    )


def _make_metadata(page_spacings: list[Optional[float]]) -> BriefMetadata:
    """Build BriefMetadata with a cover page (index 0) plus body pages."""
    pages = [_make_page(i, sp) for i, sp in enumerate(page_spacings)]
    return BriefMetadata(pages=pages, total_pages=len(pages))


# ---------------------------------------------------------------------------
# Helpers – PDF generation
# ---------------------------------------------------------------------------

def _build_pdf_bytes(leading: float, font_size: float = 12.0,
                     num_lines: int = 20) -> bytes:
    """Build a minimal single-page PDF with explicit text leading (TL).

    Uses raw PDF content-stream operators so that baseline-to-baseline
    distance is exactly *leading* points, matching how MS Word and Adobe
    encode line spacing in the ``TL`` / ``Td`` operators.
    """
    lines_ops = []
    for i in range(num_lines):
        text = f"This is line {i + 1} of the test document with controlled spacing."
        text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines_ops.append(f"({text}) Tj T*")

    stream = (
        f"BT\n"
        f"/F1 {font_size} Tf\n"
        f"{leading} TL\n"
        f"108 708 Td\n"
        + "\n".join(lines_ops)
        + "\nET"
    )
    stream_bytes = stream.encode("latin-1")

    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj",
        (b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
         b"/MediaBox [0 0 612 792] /Contents 4 0 R "
         b"/Resources << /Font << /F1 5 0 R >> >> >>\nendobj"),
        (f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
         + stream_bytes + b"\nendstream\nendobj"),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for obj in objs:
        offsets.append(len(pdf))
        pdf.extend(obj + b"\n")

    xref_off = len(pdf)
    pdf.extend(f"xref\n0 {len(objs) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets:
        pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n".encode())
    pdf.extend(f"startxref\n{xref_off}\n%%EOF\n".encode())
    return bytes(pdf)


def _pdf_blocks(leading: float, font_size: float = 12.0,
                num_lines: int = 20) -> list[dict]:
    """Generate a PDF and return its MuPDF text blocks."""
    pdf_bytes = _build_pdf_bytes(leading, font_size, num_lines)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_path = f.name
    try:
        doc = fitz.open(tmp_path)
        blocks = doc[0].get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        doc.close()
        return blocks
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _pdf_origin_spacings(leading: float, font_size: float = 12.0,
                         num_lines: int = 20) -> list[float]:
    """Return the list of actual baseline-to-baseline spacings in a generated PDF."""
    blocks = _pdf_blocks(leading, font_size, num_lines)
    origins: list[float] = []
    for b in blocks:
        if b["type"] != 0:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                if span["text"].strip():
                    origins.append(span["origin"][1])
                    break
    return [origins[i + 1] - origins[i] for i in range(len(origins) - 1)]


# ===================================================================
# Unit tests: _estimate_line_spacing with synthetic block dicts
# ===================================================================

class TestEstimateLineSpacingSynthetic:
    """Test the spacing-estimation algorithm using hand-crafted block dicts."""

    # -- MS Word standards, 12 pt ----------------------------------------

    def test_ms_word_single_12pt(self):
        """MS Word single spacing (14.4 pt) for 12 pt text."""
        ys = [100 + i * MS_WORD_SINGLE_12PT for i in range(15)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MS_WORD_SINGLE_12PT, abs=0.5)

    def test_ms_word_115_default_12pt(self):
        """MS Word 1.15 default spacing (≈16.6 pt) for 12 pt text."""
        ys = [100 + i * MS_WORD_115_12PT for i in range(15)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MS_WORD_115_12PT, abs=0.5)

    def test_ms_word_150_12pt(self):
        """MS Word 1.5-line spacing (≈21.6 pt) for 12 pt text."""
        ys = [100 + i * MS_WORD_150_12PT for i in range(15)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MS_WORD_150_12PT, abs=0.5)

    def test_ms_word_double_12pt(self):
        """MS Word double spacing (28.8 pt) for 12 pt text."""
        ys = [100 + i * MS_WORD_DOUBLE_12PT for i in range(15)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MS_WORD_DOUBLE_12PT, abs=0.5)

    # -- Adobe standards, 12 pt ------------------------------------------

    def test_adobe_auto_leading_12pt(self):
        """Adobe InDesign auto leading (14.4 pt = 120%) for 12 pt text."""
        ys = [100 + i * ADOBE_AUTO_12PT for i in range(15)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(ADOBE_AUTO_12PT, abs=0.5)

    def test_adobe_double_12pt(self):
        """Adobe 'Exactly 24 pt' double spacing for 12 pt text."""
        ys = [100 + i * ADOBE_DOUBLE_12PT for i in range(15)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(ADOBE_DOUBLE_12PT, abs=0.5)

    # -- 10 pt text -------------------------------------------------------

    def test_ms_word_single_10pt(self):
        """MS Word single spacing (12.0 pt) for 10 pt text."""
        ys = [100 + i * MS_WORD_SINGLE_10PT for i in range(15)]
        blocks = [_make_block(ys, font_size=FONT_SIZE_10)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MS_WORD_SINGLE_10PT, abs=0.5)

    def test_ms_word_double_10pt(self):
        """MS Word double spacing (24.0 pt) for 10 pt text."""
        ys = [100 + i * MS_WORD_DOUBLE_10PT for i in range(15)]
        blocks = [_make_block(ys, font_size=FONT_SIZE_10)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MS_WORD_DOUBLE_10PT, abs=0.5)

    # -- Boundary / threshold tests --------------------------------------

    def test_exactly_at_double_threshold(self):
        """Spacing exactly at MIN_DOUBLE_SPACE_PTS (20.0) is accepted."""
        ys = [100 + i * MIN_DOUBLE_SPACE_PTS for i in range(10)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(MIN_DOUBLE_SPACE_PTS, abs=0.5)

    def test_just_below_double_threshold(self):
        """Spacing just below MIN_DOUBLE_SPACE_PTS should be measurable."""
        spacing = MIN_DOUBLE_SPACE_PTS - 1.0  # 19.0 pt
        ys = [100 + i * spacing for i in range(10)]
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        assert result == pytest.approx(spacing, abs=0.5)

    # -- Edge cases -------------------------------------------------------

    def test_empty_blocks_returns_none(self):
        """No blocks → None."""
        assert _estimate_line_spacing([]) is None

    def test_image_blocks_only_returns_none(self):
        """Only image blocks (type 1) → None."""
        assert _estimate_line_spacing([_make_image_block()]) is None

    def test_single_line_block_returns_none(self):
        """A block with only one line cannot produce a spacing measurement."""
        blocks = [_make_block([200.0])]
        assert _estimate_line_spacing(blocks) is None

    def test_filters_out_tiny_spacings(self):
        """Spacings ≤ 8 pt are filtered as outliers."""
        # Two lines only 5 pt apart (sub-script overlap, etc.)
        blocks = [_make_block([100.0, 105.0])]
        assert _estimate_line_spacing(blocks) is None

    def test_filters_out_huge_spacings(self):
        """Spacings ≥ 60 pt are filtered as outliers (page break / section gap)."""
        blocks = [_make_block([100.0, 165.0])]
        assert _estimate_line_spacing(blocks) is None

    def test_median_used_not_mean(self):
        """Verify median (not mean) is returned when outliers are present."""
        # 9 lines at 24 pt spacing + 1 outlier gap at 50 pt
        ys = [100 + i * 24.0 for i in range(9)]
        ys.append(ys[-1] + 50.0)  # 50 pt gap — within filter range but large
        blocks = [_make_block(ys)]
        result = _estimate_line_spacing(blocks)
        # Median of eight 24.0 values plus one 50.0 value = 24.0
        assert result == pytest.approx(24.0, abs=0.5)

    def test_multiple_blocks(self):
        """Spacings are collected across multiple blocks."""
        block_a = _make_block([100, 124, 148])        # 24 pt spacing
        block_b = _make_block([300, 324, 348, 372])   # 24 pt spacing
        result = _estimate_line_spacing([block_a, block_b])
        assert result == pytest.approx(24.0, abs=0.5)

    def test_mixed_spacing_blocks_uses_median(self):
        """When blocks have different spacings, median wins."""
        # 3 gaps at 14 pt (single) + 5 gaps at 24 pt (double)
        single_block = _make_block([100 + i * 14.0 for i in range(4)])   # 3 gaps
        double_block = _make_block([300 + i * 24.0 for i in range(6)])   # 5 gaps
        result = _estimate_line_spacing([single_block, double_block])
        # Median of [14, 14, 14, 24, 24, 24, 24, 24] = 24
        assert result == pytest.approx(24.0, abs=0.5)

    def test_whitespace_only_spans_excluded(self):
        """Spans containing only whitespace should not contribute origins."""
        block = {
            "type": 0,
            "bbox": (108, 88, 400, 136),
            "lines": [
                {"spans": [_make_span("Real text", 100.0)],
                 "bbox": (108, 88, 400, 100), "wmode": 0, "dir": (1, 0)},
                {"spans": [_make_span("   ", 112.0), _make_span("Real text", 124.0)],
                 "bbox": (108, 112, 400, 124), "wmode": 0, "dir": (1, 0)},
            ],
        }
        result = _estimate_line_spacing([block])
        assert result == pytest.approx(24.0, abs=0.5)


# ===================================================================
# Integration tests: generated PDFs with known TL (text leading)
# ===================================================================

class TestEstimateLineSpacingPDF:
    """Verify that PDFs with exact TL values produce correct origin spacings.

    Note: MuPDF's block detection groups nearby lines into a single block
    but splits widely-spaced lines into separate blocks.  When all lines
    land in separate blocks, ``_estimate_line_spacing`` returns ``None``
    because it only measures inter-line distance *within* blocks.
    These tests document both the PDF fidelity and the block-grouping
    behavior.
    """

    # -- Verify PDF encoding fidelity (origin spacings) ------------------

    @pytest.mark.parametrize("leading,label", [
        (MS_WORD_SINGLE_12PT, "MS Word single 12pt"),
        (MS_WORD_115_12PT,    "MS Word 1.15 default 12pt"),
        (ADOBE_AUTO_12PT,     "Adobe auto 12pt"),
    ])
    def test_pdf_origins_single_range(self, leading, label):
        """Generated PDF baselines match the intended leading (single range)."""
        diffs = _pdf_origin_spacings(leading)
        assert len(diffs) > 0, f"{label}: no line spacings extracted"
        for d in diffs:
            assert d == pytest.approx(leading, abs=0.2), (
                f"{label}: expected {leading}, got {d}"
            )

    @pytest.mark.parametrize("leading,label", [
        (MS_WORD_150_12PT,    "MS Word 1.5 lines 12pt"),
        (ADOBE_DOUBLE_12PT,   "Adobe double 12pt"),
        (MS_WORD_DOUBLE_12PT, "MS Word double 12pt"),
    ])
    def test_pdf_origins_double_range(self, leading, label):
        """Generated PDF baselines match the intended leading (double range)."""
        diffs = _pdf_origin_spacings(leading)
        assert len(diffs) > 0, f"{label}: no line spacings extracted"
        for d in diffs:
            assert d == pytest.approx(leading, abs=0.2), (
                f"{label}: expected {leading}, got {d}"
            )

    # -- _estimate_line_spacing on generated PDFs ------------------------

    def test_detects_single_spacing_from_pdf(self):
        """Single-spaced PDF (14.4 pt): lines grouped in one block → detected."""
        blocks = _pdf_blocks(MS_WORD_SINGLE_12PT)
        result = _estimate_line_spacing(blocks)
        assert result is not None
        assert result == pytest.approx(MS_WORD_SINGLE_12PT, abs=0.5)

    def test_detects_word_default_115_from_pdf(self):
        """MS Word 1.15 default (16.6 pt): detected when lines are grouped."""
        blocks = _pdf_blocks(MS_WORD_115_12PT)
        result = _estimate_line_spacing(blocks)
        assert result is not None
        assert result == pytest.approx(MS_WORD_115_12PT, abs=0.5)

    def test_double_spacing_blocks_split(self):
        """Double-spaced PDF: MuPDF splits lines into separate blocks.

        This is expected behavior — MuPDF's block detection uses spatial
        proximity, so widely-spaced lines each become their own block.
        ``_estimate_line_spacing`` returns None because no block has
        multiple lines.
        """
        blocks = _pdf_blocks(MS_WORD_DOUBLE_12PT)
        text_blocks = [b for b in blocks if b["type"] == 0]
        # Each line in its own block
        for b in text_blocks:
            assert len(b.get("lines", [])) <= 1
        # Therefore no intra-block spacing can be measured
        assert _estimate_line_spacing(blocks) is None

    def test_adobe_double_blocks_split(self):
        """Adobe 24 pt double spacing: also splits into separate blocks."""
        blocks = _pdf_blocks(ADOBE_DOUBLE_12PT)
        assert _estimate_line_spacing(blocks) is None

    def test_10pt_single_from_pdf(self):
        """10 pt single spacing (12.0 pt leading) detected from PDF."""
        blocks = _pdf_blocks(MS_WORD_SINGLE_10PT, font_size=FONT_SIZE_10)
        result = _estimate_line_spacing(blocks)
        assert result is not None
        assert result == pytest.approx(MS_WORD_SINGLE_10PT, abs=0.5)


# ===================================================================
# Full-pipeline test: extract_brief on generated PDF
# ===================================================================

class TestExtractBriefLineSpacing:
    """Test ``extract_brief`` end-to-end on generated PDFs."""

    def test_extract_brief_single_spaced(self):
        """extract_brief reports single spacing for a 14.4 pt PDF."""
        from core.pdf_extract import extract_brief

        pdf_bytes = _build_pdf_bytes(MS_WORD_SINGLE_12PT)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name
        try:
            meta = extract_brief(tmp)
            assert meta.pages[0].line_spacing is not None
            assert meta.pages[0].line_spacing == pytest.approx(
                MS_WORD_SINGLE_12PT, abs=0.5
            )
            # 14.4 pt < 20.0 pt → NOT double-spaced
            assert meta.has_double_spacing is False
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_extract_brief_double_spaced_returns_none(self):
        """extract_brief gets None spacing for double-spaced PDF (block split).

        When no page reports a line_spacing value, has_double_spacing
        defaults to True (assumed compliant).
        """
        from core.pdf_extract import extract_brief

        pdf_bytes = _build_pdf_bytes(MS_WORD_DOUBLE_12PT)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name
        try:
            meta = extract_brief(tmp)
            assert meta.pages[0].line_spacing is None
            # No measurable spacing → default True
            assert meta.has_double_spacing is True
        finally:
            Path(tmp).unlink(missing_ok=True)


# ===================================================================
# FMT-009 compliance check: _check_double_spacing
# ===================================================================

class TestCheckDoubleSpacing:
    """Test the FMT-009 compliance check with synthetic metadata."""

    # -- Passing cases ---------------------------------------------------

    def test_pass_double_spaced(self):
        """Body pages at 24 pt (Adobe double) → PASS."""
        meta = _make_metadata([None, 24.0, 24.0, 24.0])
        result = _check_double_spacing(meta)
        assert result.passed is True
        assert result.check_id == "FMT-009"

    def test_pass_ms_word_double(self):
        """Body pages at 28.8 pt (MS Word double) → PASS."""
        meta = _make_metadata([None, 28.8, 28.8])
        result = _check_double_spacing(meta)
        assert result.passed is True

    def test_pass_exactly_at_threshold(self):
        """Spacing exactly at MIN_DOUBLE_SPACE_PTS (20.0) → PASS."""
        meta = _make_metadata([None, MIN_DOUBLE_SPACE_PTS, MIN_DOUBLE_SPACE_PTS])
        result = _check_double_spacing(meta)
        assert result.passed is True

    def test_pass_no_measurable_spacing_assumed_compliant(self):
        """All body pages have None spacing → assumed compliant."""
        meta = _make_metadata([None, None, None, None])
        result = _check_double_spacing(meta)
        assert result.passed is True
        assert "assumed compliant" in result.message.lower()

    def test_pass_single_page_brief(self):
        """Only cover page (no body pages) → assumed compliant."""
        meta = _make_metadata([None])
        result = _check_double_spacing(meta)
        assert result.passed is True

    # -- Failing cases ---------------------------------------------------

    def test_fail_single_spaced(self):
        """Body pages at 14.4 pt (MS Word single) → FAIL."""
        meta = _make_metadata([None, 14.4, 14.4, 14.4])
        result = _check_double_spacing(meta)
        assert result.passed is False
        assert result.severity == Severity.CORRECTION
        assert "14.4" in result.message

    def test_fail_word_default_115(self):
        """Body pages at 16.6 pt (MS Word 1.15 default) → FAIL."""
        meta = _make_metadata([None, 16.6, 16.6])
        result = _check_double_spacing(meta)
        assert result.passed is False

    def test_fail_just_below_threshold(self):
        """Spacing at 19.9 pt (just under 20.0) → FAIL."""
        meta = _make_metadata([None, 19.9, 19.9])
        result = _check_double_spacing(meta)
        assert result.passed is False

    # -- Cover page is skipped -------------------------------------------

    def test_cover_page_excluded(self):
        """Cover page (index 0) spacing does not affect the check."""
        # Cover page single-spaced, body double-spaced → PASS
        meta = _make_metadata([14.4, 24.0, 24.0])
        result = _check_double_spacing(meta)
        assert result.passed is True

    def test_cover_page_only_single_does_not_fail(self):
        """Single-spaced cover with no body spacing data → assumed compliant."""
        meta = _make_metadata([14.4, None, None])
        result = _check_double_spacing(meta)
        assert result.passed is True

    # -- Mixed spacing across body pages ---------------------------------

    def test_mixed_body_pages_median_above_threshold(self):
        """Mix of spacings whose median ≥ 20 → PASS."""
        # 5 pages at 24 pt, 2 pages at 16 pt → median = 24
        meta = _make_metadata([None, 24, 24, 24, 16, 24, 16, 24])
        result = _check_double_spacing(meta)
        assert result.passed is True

    def test_mixed_body_pages_median_below_threshold(self):
        """Mix of spacings whose median < 20 → FAIL."""
        # 5 pages at 14 pt, 2 pages at 24 pt → median = 14
        meta = _make_metadata([None, 14, 14, 14, 24, 14, 24, 14])
        result = _check_double_spacing(meta)
        assert result.passed is False

    def test_some_none_body_pages_still_checks(self):
        """Body pages with a mix of measured and None spacings."""
        # Only measurable pages count; 2 measured at 24 pt → PASS
        meta = _make_metadata([None, None, 24.0, None, 24.0])
        result = _check_double_spacing(meta)
        assert result.passed is True

    # -- Check metadata ---------------------------------------------------

    def test_check_id_and_rule(self):
        """Verify check_id, name, and rule reference."""
        meta = _make_metadata([None, 24.0])
        result = _check_double_spacing(meta)
        assert result.check_id == "FMT-009"
        assert result.name == "Double Spacing"
        assert result.rule == "32(a)(5)"

    def test_fail_includes_details(self):
        """Failed check includes details with measured value."""
        meta = _make_metadata([None, 14.4])
        result = _check_double_spacing(meta)
        assert result.passed is False
        assert result.details is not None
        assert "14.4" in result.details

    def test_severity_is_correction(self):
        """FMT-009 failures are CORRECTION severity (not REJECT)."""
        meta = _make_metadata([None, 14.4])
        result = _check_double_spacing(meta)
        assert result.severity == Severity.CORRECTION
