"""Deterministic mechanical checks for appellate brief compliance.

Checks formatting, word count limits, and numbering
against the Iowa Rules of Appellate Procedure.
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
    PAPER_HEIGHT,
    PAPER_TOLERANCE,
    PAPER_WIDTH,
    SECTION_PATTERNS,
    SMALL_CAPS_SIZE_RATIO_MAX,
    SMALL_CAPS_SIZE_RATIO_MIN,
    SMALL_CAPS_SUSPICIOUS_PAGE_PCT,
    WORD_LIMITS,
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
    results.append(_check_word_count(metadata))
    results.append(_check_oral_argument(metadata))
    results.append(_check_certificate_of_compliance(metadata))
    results.append(_check_record_citations(metadata))

    return results


def _check_paper_size(metadata: BriefMetadata) -> CheckResult:
    """FMT-001: Paper size 8.5 x 11 inches."""
    if not metadata.pages:
        return CheckResult(
            check_id="FMT-001", name="Paper Size", rule="6.903(1)(d)",
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
            check_id="FMT-001", name="Paper Size", rule="6.903(1)(d)",
            passed=False, severity=Severity.REJECT,
            message=f"Pages not 8.5\" x 11\": {_page_list(bad_pages)}.",
            details=f"Expected {PAPER_WIDTH}\" x {PAPER_HEIGHT}\". "
                    f"Page 1 is {metadata.pages[0].width_inches:.2f}\" x "
                    f"{metadata.pages[0].height_inches:.2f}\".",
        )

    return CheckResult(
        check_id="FMT-001", name="Paper Size", rule="6.903(1)(d)",
        passed=True, severity=Severity.REJECT,
        message="All pages are 8.5\" x 11\".",
    )


def _check_margins(metadata: BriefMetadata) -> list[CheckResult]:
    """FMT-002 through FMT-005: Margin checks."""
    checks = [
        ("FMT-002", "Left Margin", "left_margin_inches", MIN_LEFT_MARGIN, Severity.REJECT, "left", "1\""),
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
                check_id=check_id, name=name, rule="6.903(1)(d)",
                passed=False, severity=severity,
                message=f"{name} < {req} on {_page_list(bad_pages)}.",
                details=f"Smallest {side} margin found: {min_found:.2f}\". "
                        f"Minimum required: {req}.",
            ))
        else:
            results.append(CheckResult(
                check_id=check_id, name=name, rule="6.903(1)(d)",
                passed=True, severity=severity,
                message=f"{name} meets the {req} requirement.",
            ))

    return results


def _check_fonts(metadata: BriefMetadata) -> list[CheckResult]:
    """FMT-006, FMT-007, FMT-008: Font size, density, and style."""
    results = []

    # FMT-006: Font size >= 14pt — Rule 6.903(1)(e)
    results.append(_check_font_size_per_page(metadata))

    # FMT-007: Character density — Rule 6.903(1)(e): monospaced max 10.5 cpi
    cpi_issues = _check_chars_per_inch(metadata)
    if cpi_issues:
        results.append(CheckResult(
            check_id="FMT-007", name="Character Density", rule="6.903(1)(e)",
            passed=False, severity=Severity.CORRECTION,
            message=f"Some lines may exceed {MAX_CHARS_PER_INCH} characters per inch.",
            details=cpi_issues,
        ))
    else:
        results.append(CheckResult(
            check_id="FMT-007", name="Character Density", rule="6.903(1)(e)",
            passed=True, severity=Severity.CORRECTION,
            message=f"Character density within {MAX_CHARS_PER_INCH} characters per inch.",
        ))

    # FMT-008: Plain roman style — Rule 6.903(1)(f)
    style_issue = _check_font_style(metadata)
    if style_issue:
        results.append(CheckResult(
            check_id="FMT-008", name="Font Style", rule="6.903(1)(f)",
            passed=False, severity=Severity.NOTE,
            message="Primary body font may not be plain roman style.",
            details=style_issue,
        ))
    else:
        results.append(CheckResult(
            check_id="FMT-008", name="Font Style", rule="6.903(1)(f)",
            passed=True, severity=Severity.NOTE,
            message="Font style appears to be plain roman.",
        ))

    return results


def _is_all_uppercase(text: str) -> bool:
    """True if every alphabetic character in *text* is uppercase."""
    alpha = [c for c in text if c.isalpha()]
    return bool(alpha) and all(c.isupper() for c in alpha)


def _classify_font_span(
    font: dict,
    page_height_pts: float,
    predominant_size: float | None = None,
) -> str:
    """Classify a noncompliant font span."""
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

    # Small-caps heuristic
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
    re.compile(r"(?i)certificate\s+of\s+(service|compliance|mailing|filing)"),
    re.compile(r"(?i)table\s+of\s+(contents|authorities)"),
]


def _is_conventional_small_caps_page(
    page: "PageInfo", page_idx: int,
) -> bool:
    """Return True if the page is one where small caps are conventionally used."""
    if page_idx == 0:
        return True
    text = page.text
    return any(pat.search(text) for pat in _CONVENTIONAL_SC_PATTERNS)


def _check_font_size_per_page(metadata: BriefMetadata) -> CheckResult:
    """FMT-006: Font size >= 14pt with per-page detail, categorisation, and
    small-caps awareness."""
    threshold = MIN_FONT_SIZE_PT - FONT_SIZE_TOLERANCE
    predominant = metadata.predominant_font_size
    page_issues: list[dict] = []

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

        # Location-aware weighting for small caps
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
            check_id="FMT-006", name="Minimum Font Size", rule="6.903(1)(e)",
            passed=True, severity=Severity.REJECT,
            message=f"Font size meets the {MIN_FONT_SIZE_PT}pt minimum.",
        )

    total_nc_body = sum(pi["nc_body"] for pi in page_issues)
    total_nc_sc = sum(pi["nc_small_caps"] for pi in page_issues)

    global_min = min(pi["min_size"] for pi in page_issues)
    bad_page_nums = [pi["page"] for pi in page_issues]

    # All noncompliant chars are harmless → PASS
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
        detail = (f"Sub-{MIN_FONT_SIZE_PT}pt characters detected; all appear consistent with "
                  "conventional formatting (not undersized body text).")
        if cat_parts:
            detail += "\n" + "; ".join(cat_parts) + "."
        return CheckResult(
            check_id="FMT-006", name="Minimum Font Size", rule="6.903(1)(e)",
            passed=True, severity=Severity.REJECT,
            message=f"Font size meets the {MIN_FONT_SIZE_PT}pt minimum "
                    f"(sub-{MIN_FONT_SIZE_PT}pt characters are small caps / superscripts / headers).",
            details=detail,
        )

    # Some body violations exist
    any_serious = any(
        pi["nc_body"] >= FONT_NONCOMPLIANT_THRESHOLD for pi in page_issues
    )
    severity = Severity.REJECT if any_serious else Severity.NOTE

    page_label = "page" if len(bad_page_nums) == 1 else "pages"
    message = (
        f"Font size {global_min:.1f}pt found on {page_label} "
        f"{_page_list(bad_page_nums)}; minimum is {MIN_FONT_SIZE_PT}pt."
    )

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
            f"Note: {total_nc_sc} sub-{MIN_FONT_SIZE_PT}pt characters appear consistent with "
            f"small-caps formatting and are excluded from the violation count."
        )

    return CheckResult(
        check_id="FMT-006", name="Minimum Font Size", rule="6.903(1)(e)",
        passed=False, severity=severity,
        message=message,
        details="\n".join(lines),
    )


def _check_chars_per_inch(metadata: BriefMetadata) -> str:
    """Estimate characters per inch from page content."""
    high_density_pages = []
    for p in metadata.pages[1:]:  # skip cover
        lines = p.text.split("\n")
        for line in lines:
            stripped = line.strip()
            if len(stripped) < 10:
                continue
            text_width_inches = p.width_inches - p.left_margin_inches - p.right_margin_inches
            if text_width_inches > 0:
                cpi = len(stripped) / text_width_inches
                if cpi > MAX_CHARS_PER_INCH:
                    if (p.page_number + 1) not in high_density_pages:
                        high_density_pages.append(p.page_number + 1)
                    break

    if high_density_pages:
        return f"High character density detected on pages: {_page_list(high_density_pages)}."
    return ""


def _check_font_style(metadata: BriefMetadata) -> str:
    """Check if predominant font is roman (not italic/bold)."""
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
    spacings = []
    for p in metadata.pages[1:]:
        if p.line_spacing is not None:
            spacings.append(p.line_spacing)

    if not spacings:
        return CheckResult(
            check_id="FMT-009", name="Double Spacing", rule="6.903(1)(d)",
            passed=True, severity=Severity.CORRECTION,
            message="Unable to measure line spacing; assumed compliant.",
        )

    median = statistics.median(spacings)
    if median < MIN_DOUBLE_SPACE_PTS:
        return CheckResult(
            check_id="FMT-009", name="Double Spacing", rule="6.903(1)(d)",
            passed=False, severity=Severity.CORRECTION,
            message=f"Body text appears single-spaced (median spacing: {median:.1f}pt).",
            details=f"Double spacing requires ~28pt between baselines for 14pt text. "
                    f"Median detected: {median:.1f}pt.",
        )

    return CheckResult(
        check_id="FMT-009", name="Double Spacing", rule="6.903(1)(d)",
        passed=True, severity=Severity.CORRECTION,
        message=f"Body text appears double-spaced (median: {median:.1f}pt).",
    )


def _check_footnote_spacing(metadata: BriefMetadata) -> CheckResult:
    """FMT-010: Footnotes same typeface as text."""
    return CheckResult(
        check_id="FMT-010", name="Footnote Typeface", rule="6.903(1)(e)",
        passed=True, severity=Severity.NOTE,
        message="Footnote typeface not automatically verified; manual review recommended.",
        details="PDF extraction cannot reliably distinguish footnotes from body text.",
    )


def _check_page_numbering(metadata: BriefMetadata) -> list[CheckResult]:
    """FMT-011: Pages numbered consecutively."""
    results = []

    unnumbered = []
    for p in metadata.pages:
        if not p.has_page_number_bottom and p.text.strip():
            unnumbered.append(p.page_number + 1)

    if unnumbered:
        results.append(CheckResult(
            check_id="FMT-011", name="Page Numbering", rule="6.903(1)(d)",
            passed=False, severity=Severity.CORRECTION,
            message=f"Pages without page numbers: {_page_list(unnumbered)}.",
            details="Rule 6.903(1)(d) requires pages to be numbered consecutively.",
        ))
    else:
        results.append(CheckResult(
            check_id="FMT-011", name="Page Numbering", rule="6.903(1)(d)",
            passed=True, severity=Severity.CORRECTION,
            message="All pages have page numbers.",
        ))

    return results


def _check_word_count(metadata: BriefMetadata) -> CheckResult:
    """WC-001 through WC-003: Word count limits by brief type.

    Iowa uses word-count limits instead of page limits.
    """
    bt = metadata.brief_type
    limit = WORD_LIMITS.get(bt)

    if limit is None:
        return CheckResult(
            check_id="WC-001", name="Word Count Limit", rule="6.903(1)(g)(1)",
            passed=True, severity=Severity.REJECT,
            message="Brief type unknown; word count limit not checked.",
            applicable=False,
        )

    check_id_map = {
        BriefType.APPELLANT: "WC-001",
        BriefType.APPELLEE: "WC-001",
        BriefType.CROSS_APPEAL: "WC-001",
        BriefType.REPLY: "WC-002",
        BriefType.AMICUS: "WC-003",
    }
    rule_map = {
        BriefType.AMICUS: "6.906(4)",
    }
    check_id = check_id_map.get(bt, "WC-001")
    rule = rule_map.get(bt, "6.903(1)(g)(1)")

    wc = metadata.word_count
    if wc > limit:
        return CheckResult(
            check_id=check_id, name="Word Count Limit", rule=rule,
            passed=False, severity=Severity.REJECT,
            message=f"{bt.value.title()} brief is {wc:,} words; limit is {limit:,}.",
            details=f"Word count: {wc:,}. Maximum allowed: {limit:,}.",
        )

    return CheckResult(
        check_id=check_id, name="Word Count Limit", rule=rule,
        passed=True, severity=Severity.REJECT,
        message=f"Brief is {wc:,} words (limit: {limit:,}).",
    )


def _check_oral_argument(metadata: BriefMetadata) -> CheckResult:
    """Check for oral argument request or waiver in the brief."""
    text = metadata.full_text.upper()
    if "ORAL ARGUMENT" in text:
        return CheckResult(
            check_id="OA-001", name="Oral Argument Request/Waiver", rule="6.903(2)(9)/6.907",
            passed=True, severity=Severity.NOTE,
            message="Oral argument request or waiver found.",
        )
    return CheckResult(
        check_id="OA-001", name="Oral Argument Request/Waiver", rule="6.903(2)(9)/6.907",
        passed=False, severity=Severity.NOTE,
        message="No oral argument request or waiver found.",
        details="Rule 6.903(2)(9) requires the brief to include a request for oral argument "
                "or a statement that oral argument is not requested.",
    )


def _check_certificate_of_compliance(metadata: BriefMetadata) -> CheckResult:
    """SEC-013: Certificate of Compliance present."""
    pattern = SECTION_PATTERNS["certificate_of_compliance"]
    if re.search(pattern, metadata.full_text):
        return CheckResult(
            check_id="SEC-013", name="Certificate of Compliance", rule="6.903(1)(i)",
            passed=True, severity=Severity.CORRECTION,
            message="Certificate of Compliance found.",
        )

    return CheckResult(
        check_id="SEC-013", name="Certificate of Compliance", rule="6.903(1)(i)",
        passed=False, severity=Severity.CORRECTION,
        message="Certificate of Compliance not found.",
        details="Rule 6.903(1)(i) requires a Certificate of Compliance (Form 7).",
    )


def _check_record_citations(metadata: BriefMetadata) -> CheckResult:
    """REC-001: Record citations present in brief (Rule 6.904(2)).

    Iowa uses (App. pp. ___) and (Tr. p. ___) format instead of (R#:#).
    """
    applicable_types = {BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL}
    if metadata.brief_type not in applicable_types:
        return CheckResult(
            check_id="REC-001", name="Record Citations Present", rule="6.904(2)",
            passed=True, severity=Severity.NOTE,
            message=f"Not applicable to {metadata.brief_type.value} briefs.",
            applicable=False,
        )

    # Look for Iowa-style record citations: (App. pp. ___), (Tr. p. ___), (Conf. App. pp. ___)
    app_cites = re.findall(r"\((?:Conf\.\s+)?App\.\s+pp?\.\s*\d+", metadata.full_text, re.IGNORECASE)
    tr_cites = re.findall(r"\(Tr\.\s+pp?\.\s*\d+", metadata.full_text, re.IGNORECASE)
    count = len(app_cites) + len(tr_cites)

    if count > 0:
        return CheckResult(
            check_id="REC-001", name="Record Citations Present", rule="6.904(2)",
            passed=True, severity=Severity.NOTE,
            message=f"Found {count} record citation(s) in appendix/transcript format.",
        )

    return CheckResult(
        check_id="REC-001", name="Record Citations Present", rule="6.904(2)",
        passed=False, severity=Severity.NOTE,
        message="No record citations in (App. pp. ___) or (Tr. p. ___) format detected.",
        details="Rule 6.904(2) requires references to the appendix using (App. pp. ___) "
                "and to transcripts using (Tr. p. ___).",
    )


def _page_list(pages: list[int], max_show: int = 10) -> str:
    """Format a list of page numbers for display."""
    if len(pages) <= max_show:
        return ", ".join(str(p) for p in pages)
    shown = ", ".join(str(p) for p in pages[:max_show])
    return f"{shown} (and {len(pages) - max_show} more)"
