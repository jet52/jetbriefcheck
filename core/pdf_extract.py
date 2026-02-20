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
                    })

    # Margins: find bounding box of all content
    left_margin, right_margin, top_margin, bottom_margin = (
        _compute_margins(blocks, rect)
    )

    # Line spacing: measure baselines in text blocks
    line_spacing = _estimate_line_spacing(blocks)

    # Page number detection at bottom
    has_page_num, page_num_text = _detect_page_number(blocks, rect, text, page_idx)

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
    )


def _compute_margins(blocks: list[dict], rect: fitz.Rect) -> tuple[float, float, float, float]:
    """Compute margins in inches from text block positions.

    Page-number blocks in the bottom zone are excluded from the bottom margin
    calculation.  Rule 32(a)(4) requires 1" margins but is silent on page
    numbers; we allow page numbers (and only page numbers) to appear within
    the bottom margin zone.
    """
    if not blocks:
        # No content — return full page as margin
        return (
            rect.width / 72.0,
            rect.width / 72.0,
            rect.height / 72.0,
            rect.height / 72.0,
        )

    bottom_zone = rect.height * 0.9  # bottom 10% of page
    _PAGE_NUM_RE = re.compile(r"^[-–—]?\s*\d+\s*[-–—]?$")
    _ROMAN_RE = re.compile(r"^[-–—]?\s*[ivxlcdm]+\s*[-–—]?$", re.IGNORECASE)

    min_x = rect.width
    max_x = 0.0
    min_y = rect.height
    max_y = 0.0

    for block in blocks:
        if block["type"] != 0:  # only text blocks
            continue
        bbox = block["bbox"]

        # Skip page-number blocks in the bottom zone for margin calculation
        if bbox[1] >= bottom_zone:
            block_text = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text += span["text"]
            block_text = block_text.strip()
            if _PAGE_NUM_RE.match(block_text) or _ROMAN_RE.match(block_text):
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
    """Estimate typical line spacing in points from text block baselines."""
    spacings = []
    for block in blocks:
        if block["type"] != 0:
            continue
        lines = block.get("lines", [])
        for i in range(1, len(lines)):
            prev_baseline = lines[i - 1]["bbox"][3]  # bottom of previous line
            curr_baseline = lines[i]["bbox"][1]  # top of current line
            # More accurate: use the origin y of spans
            prev_origins = [s["origin"][1] for s in lines[i - 1].get("spans", []) if s["text"].strip()]
            curr_origins = [s["origin"][1] for s in lines[i].get("spans", []) if s["text"].strip()]
            if prev_origins and curr_origins:
                spacing = min(curr_origins) - min(prev_origins)
                if 8 < spacing < 60:  # reasonable range
                    spacings.append(spacing)

    return statistics.median(spacings) if spacings else None


def _detect_page_number(
    blocks: list[dict], rect: fitz.Rect, text: str, page_idx: int
) -> tuple[bool, Optional[str]]:
    """Detect if there's a page number at the bottom of the page."""
    bottom_zone = rect.height * 0.9  # bottom 10% of page

    for block in blocks:
        if block["type"] != 0:
            continue
        bbox = block["bbox"]
        if bbox[1] >= bottom_zone:
            block_text = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text += span["text"]
            block_text = block_text.strip()
            # Check if it looks like a page number (digits, possibly with dashes)
            if re.match(r"^[-–—]?\s*\d+\s*[-–—]?$", block_text):
                return True, block_text.strip()
            # Also match roman numerals
            if re.match(r"^[-–—]?\s*[ivxlcdm]+\s*[-–—]?$", block_text, re.IGNORECASE):
                return True, block_text.strip()

    return False, None
