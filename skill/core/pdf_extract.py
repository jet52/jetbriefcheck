"""PDF parsing with PyMuPDF: dimensions, margins, fonts, spacing, text, page numbers."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from core.constants import ADDENDUM_PATTERN
from core.models import BriefMetadata, PageInfo


def extract_brief(pdf_path: str | Path) -> BriefMetadata:
    """Extract all relevant metadata from a PDF brief."""
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))

    pages: list[PageInfo] = []
    all_text_parts: list[str] = []
    all_fonts: list[dict] = []
    line_spacings: list[float] = []
    addendum_start: Optional[int] = None

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_info = _extract_page(page, page_idx)
        pages.append(page_info)
        all_text_parts.append(page_info.text)
        all_fonts.extend(page_info.fonts)
        if page_info.line_spacing is not None:
            line_spacings.append(page_info.line_spacing)

        # Detect addendum start
        if addendum_start is None and re.search(ADDENDUM_PATTERN, page_info.text, re.MULTILINE):
            addendum_start = page_idx

    doc.close()

    full_text = "\n\n".join(all_text_parts)
    cover_text = pages[0].text if pages else ""

    # Font statistics
    font_sizes = [f["size"] for f in all_fonts if f["size"] > 0]
    font_names = [f["name"] for f in all_fonts if f["name"]]

    size_counter = Counter(round(s, 1) for s in font_sizes)
    name_counter = Counter(font_names)

    predominant_size = size_counter.most_common(1)[0][0] if size_counter else None
    predominant_font = name_counter.most_common(1)[0][0] if name_counter else None
    min_font = min(font_sizes) if font_sizes else None

    # Double spacing check
    has_double = True
    if line_spacings:
        median_spacing = statistics.median(line_spacings)
        has_double = median_spacing >= 20.0  # ~double spacing for 12pt

    # Page counts
    total_pages = len(pages)
    body_pages = addendum_start if addendum_start is not None else total_pages

    # Word count
    word_count = len(full_text.split())

    return BriefMetadata(
        total_pages=total_pages,
        body_pages=body_pages,
        addendum_start_page=addendum_start,
        cover_text=cover_text,
        full_text=full_text,
        pages=pages,
        min_font_size=min_font,
        predominant_font=predominant_font,
        predominant_font_size=predominant_size,
        has_double_spacing=has_double,
        word_count=word_count,
    )


def _extract_page(page: fitz.Page, page_idx: int) -> PageInfo:
    """Extract info from a single PDF page."""
    rect = page.rect
    width_inches = rect.width / 72.0
    height_inches = rect.height / 72.0

    # Get text blocks for margin detection
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    text = page.get_text("text")

    # Extract fonts from spans
    fonts = []
    for block in blocks:
        if block["type"] != 0:  # text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span["text"].strip():
                    fonts.append({
                        "name": span["font"],
                        "size": span["size"],
                        "flags": span["flags"],  # bold/italic flags
                        "chars": len(span["text"].strip()),
                        "origin_y": span["origin"][1],
                        "text": span["text"].strip(),  # for small caps detection
                    })

    # Margins: find bounding box of all content
    left_margin, right_margin, top_margin, bottom_margin = (
        _compute_margins(blocks, rect)
    )

    # Line spacing: measure baselines in text blocks
    line_spacing = _estimate_line_spacing(blocks)

    # Page number detection at bottom
    has_page_num, page_num_text, page_num_unknown = _detect_page_number(
        blocks, rect, text, page_idx
    )

    return PageInfo(
        page_number=page_idx,
        width_inches=width_inches,
        height_inches=height_inches,
        left_margin_inches=left_margin,
        right_margin_inches=right_margin,
        top_margin_inches=top_margin,
        bottom_margin_inches=bottom_margin,
        fonts=fonts,
        line_spacing=line_spacing,
        text=text,
        has_page_number_bottom=has_page_num,
        page_number_text=page_num_text,
        page_number_indeterminate=page_num_unknown,
    )


def _block_text(block: dict) -> str:
    """Concatenate all span text in a block, stripped."""
    return "".join(
        span["text"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ).strip()


# Page-number footer forms.  Anchored and applied only within the bottom zone,
# so they must match the whole footer — a footer carrying anything else (a case
# caption, a docket number) is content and does count against the margin.
_PAGE_NUM_RE = re.compile(
    r"^[-–—\[(]?\s*(\d+)\s*[-–—\])]?$"
)
# Labeled forms, plus bare roman numerals ("iv", "-iv-").
# "Page 5", "Page 5 of 25", "pg. 5", "5 of 25", "Page ii of 25".
# Either numbering system is allowed here — whether arabic numbering is
# required is FMT-012's question, not this recognizer's.
_PAGE_LABEL = r"(?:pages?|pg\.?)\s*"
_PAGE_OF_RE = re.compile(
    rf"^[-–—\[(]?\s*(?:{_PAGE_LABEL})?(\d+|[ivxlcdm]+)"
    r"(?:\s+of\s+(?:\d+|[ivxlcdm]+))?\s*[-–—\])]?$",
    re.IGNORECASE,
)

# A footer that *begins* with a page-number phrase but carries more text
# ("Page 1 of 2 Brief in Support of Motion...").  Block detection sometimes
# merges a running footer into one block.  Such a page IS numbered, so this
# counts for FMT-011 — but the block is not purely a page number, so it is
# NOT excluded from the margin calculation.  The asymmetry is deliberate:
# "is this page numbered?" and "may this block sit inside the bottom margin?"
# are different questions.
_PAGE_PREFIX_RE = re.compile(
    rf"^[-–—\[(]?\s*{_PAGE_LABEL}(\d+|[ivxlcdm]+)"
    r"(?:\s+of\s+(?:\d+|[ivxlcdm]+))?\b",
    re.IGNORECASE,
)

# Vertical zones, as a fraction of page height.
#
# The margin zone marks blocks low enough to intrude on the 1" bottom margin
# (which begins at 90.9% of an 11" page), and governs what may be excluded
# from the measured text area.
#
# Detection reaches higher.  Rule 32(a)(4) requires numbering "at the bottom"
# and does not say how far up that reaches; filers routinely place the number
# at 87-89%, well clear of the margin but above the margin zone.  Holding
# detection to the margin zone reported 150 pages across test-data/ as
# unnumbered when the number was plainly there.
_MARGIN_FOOTER_ZONE = 0.90
_PAGE_NUMBER_ZONE = 0.85


def _page_number_value(text: str) -> Optional[str]:
    """Return the printed page number if *text* is a page-number footer.

    Recognizes bare numerals ("5", "-5-", "[5]"), roman numerals ("iv"),
    and the labeled forms ("Page 5", "Page 5 of 25", "5 of 25").  Returns
    the bare numeral so callers can compare it directly; returns None when
    the text is not a page-number footer.
    """
    if not text:
        return None
    for pattern in (_PAGE_NUM_RE, _PAGE_OF_RE):
        match = pattern.match(text)
        if match:
            return match.group(1)
    return None


def _compute_margins(blocks: list[dict], rect: fitz.Rect) -> tuple[float, float, float, float]:
    """Compute margins in inches from text block positions.

    Two classes of block are excluded from the measured text area:

    * **Blocks with no extractable text.**  Scanned and re-imaged PDFs carry
      empty text objects that occupy space but show nothing.  They have no
      visible ink, so they cannot define a margin.
    * **Page-number blocks in the bottom zone.**  Rule 32(a)(4) requires 1"
      margins but is silent on page numbers; we allow page numbers (and only
      page numbers) to appear within the bottom margin zone.
    """
    if not blocks:
        # No content — return full page as margin
        return (
            rect.width / 72.0,
            rect.width / 72.0,
            rect.height / 72.0,
            rect.height / 72.0,
        )

    bottom_zone = rect.height * _MARGIN_FOOTER_ZONE

    min_x = rect.width
    max_x = 0.0
    min_y = rect.height
    max_y = 0.0

    for block in blocks:
        if block["type"] != 0:  # only text blocks
            continue
        bbox = block["bbox"]
        text = _block_text(block)

        # Invisible/empty text blocks define no margin anywhere on the page
        if not text:
            continue

        # Skip page-number blocks in the bottom zone for margin calculation
        if bbox[1] >= bottom_zone and _page_number_value(text) is not None:
            continue

        min_x = min(min_x, bbox[0])
        max_x = max(max_x, bbox[2])
        min_y = min(min_y, bbox[1])
        max_y = max(max_y, bbox[3])

    if max_x <= min_x or max_y <= min_y:
        return (
            rect.width / 72.0,
            rect.width / 72.0,
            rect.height / 72.0,
            rect.height / 72.0,
        )

    left = min_x / 72.0
    right = (rect.width - max_x) / 72.0
    top = min_y / 72.0
    bottom = (rect.height - max_y) / 72.0

    return left, right, top, bottom


def _estimate_line_spacing(blocks: list[dict]) -> Optional[float]:
    """Estimate typical line spacing in points from text block baselines.

    Measures both intra-block line gaps and inter-block gaps (for PDFs that
    encode each visual line as a separate block).
    """
    spacings = []

    # 1. Intra-block: gaps between lines within the same block
    for block in blocks:
        if block["type"] != 0:
            continue
        lines = block.get("lines", [])
        for i in range(1, len(lines)):
            prev_origins = [s["origin"][1] for s in lines[i - 1].get("spans", []) if s["text"].strip()]
            curr_origins = [s["origin"][1] for s in lines[i].get("spans", []) if s["text"].strip()]
            if prev_origins and curr_origins:
                spacing = min(curr_origins) - min(prev_origins)
                if 8 < spacing < 60:
                    spacings.append(spacing)

    # 2. Inter-block: gaps between consecutive single-line text blocks.
    #    Many PDF generators emit each line as its own block, so intra-block
    #    measurement finds nothing. Walk consecutive text blocks and measure
    #    baseline-to-baseline distance.
    text_blocks = [b for b in blocks if b.get("type") == 0]
    for i in range(1, len(text_blocks)):
        prev_lines = text_blocks[i - 1].get("lines", [])
        curr_lines = text_blocks[i].get("lines", [])
        if not prev_lines or not curr_lines:
            continue
        # Use the last line of prev block and first line of curr block
        prev_origins = [s["origin"][1] for s in prev_lines[-1].get("spans", []) if s["text"].strip()]
        curr_origins = [s["origin"][1] for s in curr_lines[0].get("spans", []) if s["text"].strip()]
        if prev_origins and curr_origins:
            spacing = min(curr_origins) - min(prev_origins)
            if 8 < spacing < 60:
                spacings.append(spacing)

    return statistics.median(spacings) if spacings else None


def _detect_page_number(
    blocks: list[dict], rect: fitz.Rect, text: str, page_idx: int
) -> tuple[bool, Optional[str], bool]:
    """Detect a page number at the bottom of the page.

    Returns ``(found, value, indeterminate)``.

    *value* is the bare numeral (``"5"``, ``"iv"``) rather than the raw
    footer, so a decorated footer such as ``"Page 5 of 25"`` compares equal
    to a plain ``"5"`` for FMT-012.

    *indeterminate* is True when the footer zone holds a block with no
    extractable text and no page number was found elsewhere in the zone.
    Scanned and re-imaged briefs put the number in the page image, where it
    cannot be read: something is there, but we cannot say what.  That is not
    the same as an unnumbered page, and the caller must not report it as one.
    """
    zone = rect.height * _PAGE_NUMBER_ZONE
    saw_unreadable = False

    for block in blocks:
        if block["type"] != 0:
            continue
        if block["bbox"][1] < zone:
            continue

        block_text = _block_text(block)
        if not block_text:
            saw_unreadable = True
            continue

        # A block that is only a page number, or a running footer that begins
        # with one — either way the page carries a number.
        value = _page_number_value(block_text)
        if value is None:
            prefix = _PAGE_PREFIX_RE.match(block_text)
            value = prefix.group(1) if prefix else None
        if value is not None:
            return True, value, False

    # An image in the footer zone can carry the number just as an empty text
    # block can.
    if not saw_unreadable:
        saw_unreadable = any(
            b.get("type") == 1 and b["bbox"][3] >= zone for b in blocks
        )

    return False, None, saw_unreadable
