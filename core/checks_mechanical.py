"""Deterministic mechanical checks for appellate brief compliance.

Checks formatting, page limits, cover requirements, and numbering
against the ND Rules of Appellate Procedure.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter

from core.constants import (
    FONT_NONCOMPLIANT_THRESHOLD,
    MARGIN_TOLERANCE,
    MAX_CHARS_PER_INCH,
    MIN_BOTTOM_MARGIN,
    MIN_DOUBLE_SPACE_PTS,
    MIN_FONT_SIZE_PT,
    MIN_LEFT_MARGIN,
    MIN_RIGHT_MARGIN,
    MIN_TOP_MARGIN,
    FONT_SIZE_TOLERANCE,
    PAGE_LIMITS,
    PAPER_HEIGHT,
    PAPER_TOLERANCE,
    PAPER_WIDTH,
    SECTION_PATTERNS,
    SMALL_CAPS_SIZE_RATIO_MAX,
    SMALL_CAPS_SIZE_RATIO_MIN,
    SMALL_CAPS_SUSPICIOUS_PAGE_PCT,
)
from core.models import BriefMetadata, BriefType, CheckResult, Severity


def run_mechanical_checks(metadata: BriefMetadata) -> list[CheckResult]:
    """Run all mechanical (deterministic) checks and return results."""
    results = []

    results.append(_check_paper_size(metadata))
    results.extend(_check_margins(metadata))
    results.extend(_check_fonts(metadata))
    results.append(_check_double_spacing(metadata))
    results.append(_check_footnote_spacing(metadata))
    results.extend(_check_page_numbering(metadata))
    results.append(_check_page_limit(metadata))
    results.append(_check_cover_color(metadata))
    results.append(_check_oral_argument(metadata))
    results.append(_check_paragraph_numbering(metadata))
    results.append(_check_certificate_of_compliance(metadata))
    results.append(_check_record_citations(metadata))

    return results


def _check_paper_size(metadata: BriefMetadata) -> CheckResult:
    """FMT-001: Paper size 8.5 x 11 inches."""
    if not metadata.pages:
        return CheckResult(
            check_id="FMT-001", name="Paper Size", rule="32(a)(4)",
            passed=False, severity=Severity.REJECT,
            message="No pages found in PDF.",
        )

    bad_pages = []
    for p in metadata.pages:
        if (abs(p.width_inches - PAPER_WIDTH) > PAPER_TOLERANCE or
                abs(p.height_inches - PAPER_HEIGHT) > PAPER_TOLERANCE):
            bad_pages.append(p.page_number + 1)

    if bad_pages:
        return CheckResult(
            check_id="FMT-001", name="Paper Size", rule="32(a)(4)",
            passed=False, severity=Severity.REJECT,
            message=f"Pages not 8.5\" x 11\": {_page_list(bad_pages)}.",
            details=f"Expected {PAPER_WIDTH}\" x {PAPER_HEIGHT}\". "
                    f"Page 1 is {metadata.pages[0].width_inches:.2f}\" x "
                    f"{metadata.pages[0].height_inches:.2f}\".",
        )

    return CheckResult(
        check_id="FMT-001", name="Paper Size", rule="32(a)(4)",
        passed=True, severity=Severity.REJECT,
        message="All pages are 8.5\" x 11\".",
    )


def _check_margins(metadata: BriefMetadata) -> list[CheckResult]:
    """FMT-002 through FMT-005: Margin checks."""
    checks = [
        ("FMT-002", "Left Margin", "left_margin_inches", MIN_LEFT_MARGIN, Severity.REJECT, "left", "1.5\""),
        ("FMT-003", "Right Margin", "right_margin_inches", MIN_RIGHT_MARGIN, Severity.CORRECTION, "right", "1\""),
        ("FMT-004", "Top Margin", "top_margin_inches", MIN_TOP_MARGIN, Severity.CORRECTION, "top", "1\""),
        ("FMT-005", "Bottom Margin", "bottom_margin_inches", MIN_BOTTOM_MARGIN, Severity.CORRECTION, "bottom", "1\""),
    ]

    results = []
    for check_id, name, attr, minimum, severity, side, req in checks:
        bad_pages = []
        min_found = None
        for p in metadata.pages:
            val = getattr(p, attr)
            if val < minimum - MARGIN_TOLERANCE:
                bad_pages.append(p.page_number + 1)
                if min_found is None or val < min_found:
                    min_found = val

        if bad_pages:
            results.append(CheckResult(
                check_id=check_id, name=name, rule="32(a)(4)",
                passed=False, severity=severity,
                message=f"{name} < {req} on {_page_list(bad_pages)}.",
                details=f"Smallest {side} margin found: {min_found:.2f}\". "
                        f"Minimum required: {req}.",
            ))
        else:
            results.append(CheckResult(
                check_id=check_id, name=name, rule="32(a)(4)",
                passed=True, severity=severity,
                message=f"{name} meets the {req} requirement.",
            ))

    return results


def _check_fonts(metadata: BriefMetadata) -> list[CheckResult]:
    """FMT-006, FMT-007, FMT-008: Font size, density, and style."""
    results = []

    # FMT-006: Font size >= 12pt — Rule 32(a)(5): "The typeface must be 12 point or larger"
    results.append(_check_font_size_per_page(metadata))

    # FMT-007: Max 16 characters per inch — Rule 32(a)(5): "no more than 16 characters per inch"
    cpi_issues = _check_chars_per_inch(metadata)
    if cpi_issues:
        results.append(CheckResult(
            check_id="FMT-007", name="Character Density", rule="32(a)(5)",
            passed=False, severity=Severity.CORRECTION,
            message="Some lines may exceed 16 characters per inch.",
            details=cpi_issues,
        ))
    else:
        results.append(CheckResult(
            check_id="FMT-007", name="Character Density", rule="32(a)(5)",
            passed=True, severity=Severity.CORRECTION,
            message="Character density within 16 characters per inch.",
        ))

    # FMT-008: Plain roman style — Rule 32(a)(6): "set in a plain, roman style"
    style_issue = _check_font_style(metadata)
    if style_issue:
        results.append(CheckResult(
            check_id="FMT-008", name="Font Style", rule="32(a)(6)",
            passed=False, severity=Severity.NOTE,
            message="Primary body font may not be plain roman style.",
            details=style_issue,
        ))
    else:
        results.append(CheckResult(
            check_id="FMT-008", name="Font Style", rule="32(a)(6)",
            passed=True, severity=Severity.NOTE,
            message="Font style appears to be plain roman.",
        ))

    return results


def _is_all_uppercase(text: str) -> bool:
    """True if every alphabetic character in *text* is uppercase.

    Returns False when there are no alphabetic characters at all (pure
    digits / punctuation cannot be small caps).
    """
    alpha = [c for c in text if c.isalpha()]
    return bool(alpha) and all(c.isupper() for c in alpha)


def _classify_font_span(
    font: dict,
    page_height_pts: float,
    predominant_size: float | None = None,
) -> str:
    """Classify a noncompliant font span.

    Returns one of:
      - ``"header_footer"`` — origin_y in top or bottom 10 % of the page
      - ``"superscript"``   — PyMuPDF superscript flag set, or ≤ 4 chars at
        small size (footnote markers / ordinal suffixes)
      - ``"small_caps"``    — all-uppercase text at 55–85 % of the predominant
        body font size (conventional small-caps formatting)
      - ``"body"``          — everything else (genuine undersized body text)
    """
    origin_y = font.get("origin_y", page_height_pts / 2)
    top_zone = page_height_pts * 0.10
    bottom_zone = page_height_pts * 0.90

    if origin_y <= top_zone or origin_y >= bottom_zone:
        return "header_footer"

    flags = font.get("flags", 0)
    is_superscript = bool(flags & 1)  # bit 0
    if is_superscript:
        return "superscript"

    # Short digit-only text at small size — likely footnote marker or ordinal
    chars = font.get("chars", 0)
    if chars <= 4 and font["size"] < MIN_FONT_SIZE_PT - FONT_SIZE_TOLERANCE:
        return "superscript"

    # --- Layer 1: Small-caps heuristic ---
    # Small caps in a PDF are encoded as uppercase glyphs at a reduced point
    # size (typically 60-80 % of the full body font).  Detect them by
    # checking (a) all alpha chars are uppercase and (b) the size ratio
    # falls within the expected small-caps band.
    if predominant_size and predominant_size > 0:
        text = font.get("text", "")
        if text and _is_all_uppercase(text):
            ratio = font["size"] / predominant_size
            if SMALL_CAPS_SIZE_RATIO_MIN <= ratio <= SMALL_CAPS_SIZE_RATIO_MAX:
                return "small_caps"

    return "body"


# Patterns that identify pages where small caps are conventionally expected.
_CONVENTIONAL_SC_PATTERNS = [
    re.compile(r"(?i)respectfully\s+submitted"),
    re.compile(r"(?i)certificate\s+of\s+(service|compliance|mailing)"),
    re.compile(r"(?i)table\s+of\s+(contents|authorities)"),
]


def _is_conventional_small_caps_page(
    page: "PageInfo", page_idx: int,
) -> bool:
    """Return True if the page is one where small caps are conventionally used.

    Conventional pages:
    - Cover page (page 0): court name, party designations
    - TOC / TOA pages
    - Certificate of service / compliance / signature blocks
    """
    if page_idx == 0:
        return True
    text = page.text
    return any(pat.search(text) for pat in _CONVENTIONAL_SC_PATTERNS)


def _check_font_size_per_page(metadata: BriefMetadata) -> CheckResult:
    """FMT-006: Font size >= 12pt with per-page detail, categorisation, and
    small-caps awareness.

    Three-layer approach:
      1. **Heuristic detection** — each sub-12pt span is classified as
         header/footer, superscript, small_caps, or body.
      2. **Location-aware weighting** — small caps on conventional pages
         (cover, TOC/TOA, certificate / signature blocks) are always treated
         as benign.  On non-conventional pages, small caps exceeding a
         per-page percentage threshold are reclassified as body text
         (guards against whole paragraphs set in small caps to evade the
         font-size rule).
      3. **Graduated severity** —
           * all noncompliant chars are harmless (sc + sup + hf) → PASS
             with informational note
           * some ambiguous body chars but below threshold → NOTE
           * substantial body text violations → REJECT
    """
    threshold = MIN_FONT_SIZE_PT - FONT_SIZE_TOLERANCE
    predominant = metadata.predominant_font_size
    page_issues: list[dict] = []  # one entry per page that has noncompliant chars

    for p in metadata.pages:
        if not p.fonts:
            continue

        page_height_pts = p.height_inches * 72.0
        total_chars = 0
        nc_body = 0
        nc_hf = 0
        nc_super = 0
        nc_small_caps = 0
        min_size_on_page: float | None = None

        for f in p.fonts:
            char_count = f.get("chars", 1)
            total_chars += char_count

            if f["size"] < threshold:
                category = _classify_font_span(f, page_height_pts, predominant)
                if category == "header_footer":
                    nc_hf += char_count
                elif category == "superscript":
                    nc_super += char_count
                elif category == "small_caps":
                    nc_small_caps += char_count
                else:
                    nc_body += char_count

                if min_size_on_page is None or f["size"] < min_size_on_page:
                    min_size_on_page = f["size"]

        # --- Layer 2: location-aware weighting ---
        # On non-conventional pages, if small caps exceed the suspicious
        # threshold they are reclassified as body text.
        if nc_small_caps > 0:
            is_conventional = _is_conventional_small_caps_page(p, p.page_number)
            if not is_conventional and total_chars > 0:
                sc_pct = nc_small_caps / total_chars * 100
                if sc_pct > SMALL_CAPS_SUSPICIOUS_PAGE_PCT:
                    nc_body += nc_small_caps
                    nc_small_caps = 0

        nc_total = nc_body + nc_hf + nc_super + nc_small_caps
        if nc_total > 0:
            page_issues.append({
                "page": p.page_number + 1,
                "total_chars": total_chars,
                "nc_total": nc_total,
                "nc_body": nc_body,
                "nc_hf": nc_hf,
                "nc_super": nc_super,
                "nc_small_caps": nc_small_caps,
                "min_size": min_size_on_page,
            })

    if not page_issues:
        return CheckResult(
            check_id="FMT-006", name="Minimum Font Size", rule="32(a)(5)",
            passed=True, severity=Severity.REJECT,
            message=f"Font size meets the {MIN_FONT_SIZE_PT}pt minimum.",
        )

    # --- Layer 3: graduated severity ---
    total_nc_body = sum(pi["nc_body"] for pi in page_issues)
    total_nc_sc = sum(pi["nc_small_caps"] for pi in page_issues)

    global_min = min(pi["min_size"] for pi in page_issues)
    bad_page_nums = [pi["page"] for pi in page_issues]

    # (a) All noncompliant chars are harmless → PASS with informational note
    if total_nc_body == 0:
        cat_parts = []
        if total_nc_sc:
            sc_pages = sorted({pi["page"] for pi in page_issues if pi["nc_small_caps"]})
            cat_parts.append(f"small caps on pages {_page_list(sc_pages)}")
        total_hf = sum(pi["nc_hf"] for pi in page_issues)
        if total_hf:
            hf_pages = sorted({pi["page"] for pi in page_issues if pi["nc_hf"]})
            cat_parts.append(f"headers/footers on pages {_page_list(hf_pages)}")
        total_sup = sum(pi["nc_super"] for pi in page_issues)
        if total_sup:
            sup_pages = sorted({pi["page"] for pi in page_issues if pi["nc_super"]})
            cat_parts.append(f"superscripts on pages {_page_list(sup_pages)}")
        detail = ("Sub-12pt characters detected; all appear consistent with "
                  "conventional formatting (not undersized body text).")
        if cat_parts:
            detail += "\n" + "; ".join(cat_parts) + "."
        return CheckResult(
            check_id="FMT-006", name="Minimum Font Size", rule="32(a)(5)",
            passed=True, severity=Severity.REJECT,
            message=f"Font size meets the {MIN_FONT_SIZE_PT}pt minimum "
                    f"(sub-12pt characters are small caps / superscripts / headers).",
            details=detail,
        )

    # (b) / (c) Some body violations exist — determine severity
    any_serious = any(
        pi["nc_body"] >= FONT_NONCOMPLIANT_THRESHOLD for pi in page_issues
    )
    severity = Severity.REJECT if any_serious else Severity.NOTE

    page_label = "page" if len(bad_page_nums) == 1 else "pages"
    message = (
        f"Font size {global_min:.1f}pt found on {page_label} "
        f"{_page_list(bad_page_nums)}; minimum is {MIN_FONT_SIZE_PT}pt."
    )

    # Build per-page breakdown
    lines = [
        f"Predominant font size: {metadata.predominant_font_size}pt. "
        f"Smallest detected: {global_min:.1f}pt.",
        "",
        "Per-page breakdown:",
    ]
    for pi in page_issues:
        pct = pi["nc_total"] / pi["total_chars"] * 100 if pi["total_chars"] else 0
        parts = []
        if pi["nc_body"]:
            parts.append(f"{pi['nc_body']} body")
        if pi["nc_small_caps"]:
            parts.append(f"{pi['nc_small_caps']} small caps")
        if pi["nc_hf"]:
            parts.append(f"{pi['nc_hf']} header/footer")
        if pi["nc_super"]:
            parts.append(f"{pi['nc_super']} superscript")
        breakdown = ", ".join(parts)
        lines.append(
            f"  Page {pi['page']}: {pi['nc_total']} of {pi['total_chars']:,} chars "
            f"({pct:.1f}%) noncompliant — {breakdown}"
        )

    if total_nc_sc > 0:
        lines.append("")
        lines.append(
            f"Note: {total_nc_sc} sub-12pt characters appear consistent with "
            f"small-caps formatting and are excluded from the violation count."
        )

    return CheckResult(
        check_id="FMT-006", name="Minimum Font Size", rule="32(a)(5)",
        passed=False, severity=severity,
        message=message,
        details="\n".join(lines),
    )


def _check_chars_per_inch(metadata: BriefMetadata) -> str:
    """Estimate characters per inch from page content."""
    # Use body pages only, skip cover
    high_density_pages = []
    for p in metadata.pages[1:]:  # skip cover
        lines = p.text.split("\n")
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 10:
                continue
            # Estimate line width from margins
            text_width_inches = p.width_inches - p.left_margin_inches - p.right_margin_inches
            if text_width_inches > 0:
                cpi = len(stripped) / text_width_inches
                if cpi > MAX_CHARS_PER_INCH:
                    if (p.page_number + 1) not in high_density_pages:
                        high_density_pages.append(p.page_number + 1)
                    break  # one line per page is enough

    if high_density_pages:
        return f"High character density detected on pages: {_page_list(high_density_pages)}."
    return ""


def _check_font_style(metadata: BriefMetadata) -> str:
    """Check if predominant font is roman (not italic/bold)."""
    # PyMuPDF font flags: bit 0=superscript, bit 1=italic, bit 4=bold
    all_fonts = []
    for p in metadata.pages[1:]:  # skip cover
        all_fonts.extend(p.fonts)

    if not all_fonts:
        return ""

    flag_counter = Counter()
    for f in all_fonts:
        flags = f.get("flags", 0)
        is_italic = bool(flags & 2)
        is_bold = bool(flags & 16)
        if is_italic and is_bold:
            flag_counter["bold-italic"] += 1
        elif is_italic:
            flag_counter["italic"] += 1
        elif is_bold:
            flag_counter["bold"] += 1
        else:
            flag_counter["roman"] += 1

    total = sum(flag_counter.values())
    if total == 0:
        return ""

    roman_pct = flag_counter.get("roman", 0) / total
    if roman_pct < 0.5:
        dominant = flag_counter.most_common(1)[0]
        return (f"Only {roman_pct:.0%} of text spans are plain roman. "
                f"Most common style: {dominant[0]} ({dominant[1]}/{total} spans).")
    return ""


def _check_double_spacing(metadata: BriefMetadata) -> CheckResult:
    """FMT-009: Body text is double-spaced."""
    # Collect line spacings from body pages (skip cover)
    spacings = []
    for p in metadata.pages[1:]:
        if p.line_spacing is not None:
            spacings.append(p.line_spacing)

    if not spacings:
        return CheckResult(
            check_id="FMT-009", name="Double Spacing", rule="32(a)(5)",
            passed=True, severity=Severity.CORRECTION,
            message="Unable to measure line spacing; assumed compliant.",
        )

    median = statistics.median(spacings)
    if median < MIN_DOUBLE_SPACE_PTS:
        return CheckResult(
            check_id="FMT-009", name="Double Spacing", rule="32(a)(5)",
            passed=False, severity=Severity.CORRECTION,
            message=f"Body text appears single-spaced (median spacing: {median:.1f}pt).",
            details=f"Double spacing requires ~24pt between baselines for 12pt text. "
                    f"Median detected: {median:.1f}pt.",
        )

    return CheckResult(
        check_id="FMT-009", name="Double Spacing", rule="32(a)(5)",
        passed=True, severity=Severity.CORRECTION,
        message=f"Body text appears double-spaced (median: {median:.1f}pt).",
    )


def _check_footnote_spacing(metadata: BriefMetadata) -> CheckResult:
    """FMT-010: Footnotes double-spaced, same typeface."""
    # Footnote detection is imprecise from PDF extraction alone.
    # We flag this as a NOTE-level advisory check.
    return CheckResult(
        check_id="FMT-010", name="Footnote Spacing", rule="32(a)(5)",
        passed=True, severity=Severity.NOTE,
        message="Footnote spacing not automatically verified; manual review recommended.",
        details="PDF extraction cannot reliably distinguish footnotes from body text.",
    )


def _check_page_numbering(metadata: BriefMetadata) -> list[CheckResult]:
    """FMT-011 and FMT-012: Page numbering."""
    results = []

    # FMT-011: Pages numbered at bottom
    unnumbered = []
    for p in metadata.pages:
        if not p.has_page_number_bottom and p.text.strip():
            unnumbered.append(p.page_number + 1)

    if unnumbered:
        results.append(CheckResult(
            check_id="FMT-011", name="Page Numbers at Bottom", rule="32(a)(4)",
            passed=False, severity=Severity.CORRECTION,
            message=f"Pages without bottom page numbers: {_page_list(unnumbered)}.",
            details="Rule 32(a)(4) requires pages to be numbered at the bottom.",
        ))
    else:
        results.append(CheckResult(
            check_id="FMT-011", name="Page Numbers at Bottom", rule="32(a)(4)",
            passed=True, severity=Severity.CORRECTION,
            message="All pages have bottom page numbers.",
        ))

    # FMT-012: Numbering starts with "1" on cover
    if metadata.pages:
        cover = metadata.pages[0]
        starts_with_one = (
            cover.has_page_number_bottom and
            cover.page_number_text is not None and
            cover.page_number_text.strip().strip("-–—").strip() == "1"
        )
        if not starts_with_one:
            results.append(CheckResult(
                check_id="FMT-012", name="Numbering Starts at 1", rule="32(a)(4)",
                passed=False, severity=Severity.NOTE,
                message="Cover page number is not \"1\" or not detected.",
                details=f"Detected cover page number: {cover.page_number_text!r}.",
            ))
        else:
            results.append(CheckResult(
                check_id="FMT-012", name="Numbering Starts at 1", rule="32(a)(4)",
                passed=True, severity=Severity.NOTE,
                message="Page numbering starts with \"1\" on the cover.",
            ))

    return results


def _check_page_limit(metadata: BriefMetadata) -> CheckResult:
    """PG-001 through PG-004: Page limits by brief type."""
    bt = metadata.brief_type
    limit = PAGE_LIMITS.get(bt)

    if limit is None:
        check_id = "PG-001"
        return CheckResult(
            check_id=check_id, name="Page Limit", rule="32(a)(8)",
            passed=True, severity=Severity.REJECT,
            message="Brief type unknown; page limit not checked.",
            applicable=False,
        )

    # Determine check ID and rule citation
    check_id_map = {
        BriefType.APPELLANT: "PG-001",
        BriefType.APPELLEE: "PG-001",
        BriefType.CROSS_APPEAL: "PG-001",
        BriefType.REPLY: "PG-002",
        BriefType.AMICUS: "PG-003",
    }
    # Amicus page limit is in Rule 29(a)(5); all others in Rule 32(a)(8)
    rule_map = {
        BriefType.AMICUS: "29(a)(5)",
    }
    check_id = check_id_map.get(bt, "PG-001")
    rule = rule_map.get(bt, "32(a)(8)")

    body = metadata.body_pages
    if body > limit:
        return CheckResult(
            check_id=check_id, name="Page Limit", rule=rule,
            passed=False, severity=Severity.REJECT,
            message=f"{bt.value.title()} brief is {body} pages; limit is {limit}.",
            details=f"Body pages (excluding addendum): {body}. "
                    f"Addendum starts at page {metadata.addendum_start_page + 1 if metadata.addendum_start_page else 'N/A'}.",
        )

    return CheckResult(
        check_id=check_id, name="Page Limit", rule=rule,
        passed=True, severity=Severity.REJECT,
        message=f"Brief is {body} pages (limit: {limit}).",
    )


def _check_cover_color(metadata: BriefMetadata) -> CheckResult:
    """COV-001: Cover color matches brief type.

    We cannot detect physical cover color from PDF. This check is advisory.
    """
    from core.constants import COVER_COLORS
    expected = COVER_COLORS.get(metadata.brief_type)
    if expected:
        return CheckResult(
            check_id="COV-001", name="Cover Color", rule="32(a)(2)",
            passed=True, severity=Severity.CORRECTION,
            message=f"Cover color should be {expected} for {metadata.brief_type.value} brief. "
                    "Cannot verify from PDF; manual check required.",
            details="PDF analysis cannot detect physical cover color.",
        )
    return CheckResult(
        check_id="COV-001", name="Cover Color", rule="32(a)(2)",
        passed=True, severity=Severity.CORRECTION,
        message="Cover color check not applicable (unknown brief type).",
        applicable=False,
    )


def _check_oral_argument(metadata: BriefMetadata) -> CheckResult:
    """COV-002: 'ORAL ARGUMENT REQUESTED' on cover."""
    cover = metadata.cover_text.upper()
    if "ORAL ARGUMENT" in cover:
        return CheckResult(
            check_id="COV-002", name="Oral Argument Notation", rule="28(h)/34(a)(1)(C)",
            passed=True, severity=Severity.NOTE,
            message="Cover includes oral argument request notation.",
        )
    return CheckResult(
        check_id="COV-002", name="Oral Argument Notation", rule="28(h)/34(a)(1)(C)",
        passed=False, severity=Severity.NOTE,
        message="No 'ORAL ARGUMENT REQUESTED' found on cover page.",
        details="Rule 28(h) requires 'ORAL ARGUMENT REQUESTED' on the cover; "
                "Rule 34(a)(1)(C) provides that oral argument generally will not be scheduled "
                "if no request has been made.",
    )


def _check_paragraph_numbering(metadata: BriefMetadata) -> CheckResult:
    """CNT-004: Paragraphs numbered with arabic numerals."""
    # Look for paragraph numbering pattern: [1], [2], etc. or ¶1, ¶2
    # In ND practice, paragraphs are typically numbered [1], [2], etc.
    text = metadata.full_text
    bracket_nums = re.findall(r"\[\d+\]", text)
    para_symbols = re.findall(r"¶\s*\d+", text)

    has_numbering = len(bracket_nums) >= 3 or len(para_symbols) >= 3

    if has_numbering:
        return CheckResult(
            check_id="CNT-004", name="Paragraph Numbering", rule="32(a)(7)",
            passed=True, severity=Severity.CORRECTION,
            message="Paragraphs appear to use arabic numeral numbering.",
        )

    return CheckResult(
        check_id="CNT-004", name="Paragraph Numbering", rule="32(a)(7)",
        passed=False, severity=Severity.CORRECTION,
        message="Paragraph numbering with arabic numerals not detected.",
        details="Rule 32(a)(7) requires paragraphs to be numbered with arabic numerals. "
                f"Found {len(bracket_nums)} bracket-number patterns and "
                f"{len(para_symbols)} paragraph-symbol patterns.",
    )


def _check_certificate_of_compliance(metadata: BriefMetadata) -> CheckResult:
    """SEC-013: Certificate of Compliance present."""
    pattern = SECTION_PATTERNS["certificate_of_compliance"]
    if re.search(pattern, metadata.full_text):
        return CheckResult(
            check_id="SEC-013", name="Certificate of Compliance", rule="32(d)",
            passed=True, severity=Severity.CORRECTION,
            message="Certificate of Compliance found.",
        )

    return CheckResult(
        check_id="SEC-013", name="Certificate of Compliance", rule="32(d)",
        passed=False, severity=Severity.CORRECTION,
        message="Certificate of Compliance not found.",
        details="Rule 32(d) requires a Certificate of Compliance.",
    )


def _check_record_citations(metadata: BriefMetadata) -> CheckResult:
    """REC-001: Record citations present in brief (Rule 30(a))."""
    # Only applicable to briefs that cite the record
    applicable_types = {BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL}
    if metadata.brief_type not in applicable_types:
        return CheckResult(
            check_id="REC-001", name="Record Citations Present", rule="30(a)",
            passed=True, severity=Severity.NOTE,
            message=f"Not applicable to {metadata.brief_type.value} briefs.",
            applicable=False,
        )

    # Look for (R{index}:{page}) pattern per Rule 30(b)(1)
    record_cites = re.findall(r"\(R\d+:\d+", metadata.full_text)
    count = len(record_cites)

    if count > 0:
        return CheckResult(
            check_id="REC-001", name="Record Citations Present", rule="30(a)",
            passed=True, severity=Severity.NOTE,
            message=f"Found {count} record citation(s) in (R#:#) format.",
        )

    return CheckResult(
        check_id="REC-001", name="Record Citations Present", rule="30(a)",
        passed=False, severity=Severity.NOTE,
        message="No record citations in (R#:#) format detected.",
        details="Rule 30(a) requires references to the record with register of actions "
                "index numbers. Rule 30(b)(1) specifies the (R{index}:{page}) format.",
    )


def _page_list(pages: list[int], max_show: int = 10) -> str:
    """Format a list of page numbers for display."""
    if len(pages) <= max_show:
        return ", ".join(str(p) for p in pages)
    shown = ", ".join(str(p) for p in pages[:max_show])
    return f"{shown} (and {len(pages) - max_show} more)"
