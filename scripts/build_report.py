#!/usr/bin/env python3
"""Merge mechanical + semantic results and build the HTML compliance report.

Usage:
    python build_report.py --intermediate <path> --semantic <path> [--output-dir DIR]

Takes the intermediate JSON (from check_brief.py --mechanical-only) and
semantic JSON (from Claude Code analysis), merges them, applies hard-rule
recommendation logic, and generates the final HTML report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

# Derive project root from script location (works from repo or symlinked skill dir)
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from core.models import BriefMetadata, BriefType, CheckResult, ComplianceReport, Recommendation, Severity
from core.report_builder import build_html_report
from core.version_check import get_version_stamp


def _parse_results(items: list[dict]) -> list[CheckResult]:
    """Convert a list of JSON dicts into CheckResult objects."""
    results = []
    for item in items:
        results.append(CheckResult(
            check_id=item["check_id"],
            name=item["name"],
            rule=item["rule"],
            passed=item["passed"],
            severity=Severity(item["severity"]),
            message=item["message"],
            details=item.get("details"),
            applicable=item.get("applicable", True),
        ))
    return results


def _hard_rule_recommendation(results: list[CheckResult]) -> tuple[Recommendation, str]:
    """Determine recommendation from severity levels (no API call)."""
    failed = [r for r in results if r.failed]
    has_reject = any(r.severity == Severity.REJECT for r in failed)
    has_correction = any(r.severity == Severity.CORRECTION for r in failed)

    if has_reject:
        reject_checks = [r for r in failed if r.severity == Severity.REJECT]
        reasoning = (
            f"REJECT due to {len(reject_checks)} critical failure(s): "
            + "; ".join(f"{r.check_id} ({r.name})" for r in reject_checks)
        )
        return Recommendation.REJECT, reasoning

    if has_correction:
        correction_checks = [r for r in failed if r.severity == Severity.CORRECTION]
        reasoning = (
            f"Correction letter recommended due to {len(correction_checks)} issue(s): "
            + "; ".join(f"{r.check_id} ({r.name})" for r in correction_checks)
        )
        return Recommendation.CORRECTION_LETTER, reasoning

    return Recommendation.ACCEPT, "All checks passed."


def _extract_case_info(cover_text: str, pdf_path: str) -> tuple[str, str, str]:
    """Extract case number, short title, and brief label from cover text and filename.

    Returns (case_number, case_title, brief_label).
    """
    case_number = ""
    case_title = ""
    brief_label = ""

    # Case number: look for "Supreme Court No. 20990001" or similar
    m = re.search(r"Supreme Court No\.?\s*(\d{8})", cover_text, re.IGNORECASE)
    if m:
        case_number = m.group(1)

    # Brief label: look for "[AMENDED] BRIEF OF DEFENDANT-APPELLANT" etc. on one line
    m = re.search(
        r"((?:AMENDED\s+)?(?:REPLY\s+)?BRIEF\s+OF\s+\S[^\n]{3,60})",
        cover_text,
    )
    if m:
        brief_label = m.group(1).strip().rstrip(",")
        # Title-case it for readability
        brief_label = brief_label.title()

    # Case title: look for plaintiff name on the line before "Plaintiff"
    # and defendant name on the line after "vs."
    plaintiff = ""
    defendant = ""
    # Match the last non-empty, non-paren line before "Plaintiff"
    m = re.search(r"\n\s*([A-Z][a-zA-Z.\- ]+?)\s*,?\s*\)?\s*\n(?:\s*\)?\s*\n)*\s*(?:\)?\s*\n\s*)*Plaintiff", cover_text)
    if m:
        plaintiff = m.group(1).strip().rstrip(",")
    # Match the first name line after "vs."
    m2 = re.search(r"vs\.?\s*\)?\s*\n(?:\s*\)?\s*\n)*\s*([A-Z][a-zA-Z.\- ]+?)\s*,?\s*\)?\s*\n", cover_text)
    if m2:
        defendant = m2.group(1).strip().rstrip(",")

    if plaintiff and defendant:
        case_title = f"{plaintiff} v. {defendant}"

    if not case_title:
        # Fallback: derive from PDF filename (e.g., "20990001_Example-Case_Apt-Br.pdf")
        stem = Path(pdf_path).stem
        # Strip leading case number
        name_part = re.sub(r"^\d+_", "", stem)
        # Strip trailing brief-type suffix
        name_part = re.sub(r"_(Apt|Ape|Apc|Ami|Rep)-?Br.*$", "", name_part, flags=re.IGNORECASE)
        # Convert hyphens to spaces, "v" to "v."
        name_part = name_part.replace("-", " ")
        name_part = re.sub(r"\bv\b", "v.", name_part)
        case_title = name_part.strip()

    return case_number, case_title, brief_label


def main():
    parser = argparse.ArgumentParser(description="Merge results and build HTML compliance report.")
    parser.add_argument("--intermediate", required=True, help="Path to intermediate JSON from check_brief.py")
    parser.add_argument("--semantic", required=True, help="Path to semantic results JSON from Claude Code")
    parser.add_argument("--output-dir", default=None, help="Directory for HTML report (default: same as intermediate)")
    parser.add_argument("--reasoning", default=None, help="Optional reasoning text for the report summary")
    args = parser.parse_args()

    intermediate_path = Path(args.intermediate)
    semantic_path = Path(args.semantic)

    if not intermediate_path.exists():
        print(f"Error: Intermediate file not found: {intermediate_path}", file=sys.stderr)
        sys.exit(1)
    if not semantic_path.exists():
        print(f"Error: Semantic file not found: {semantic_path}", file=sys.stderr)
        sys.exit(1)

    # Load intermediate (mechanical) data
    intermediate = json.loads(intermediate_path.read_text(encoding="utf-8"))
    mech_results = _parse_results(intermediate["mechanical_results"])

    # Load semantic results
    semantic_data = json.loads(semantic_path.read_text(encoding="utf-8"))
    sem_results = _parse_results(semantic_data["semantic_results"])

    # Merge all results
    all_results = mech_results + sem_results

    # Hard-rule recommendation (no API)
    recommendation, reasoning = _hard_rule_recommendation(all_results)

    # Use caller-provided reasoning if available
    if args.reasoning:
        reasoning = args.reasoning

    # Build minimal metadata for the report
    brief_type = BriefType(intermediate["brief_type"])
    metadata = BriefMetadata(
        brief_type=brief_type,
        total_pages=intermediate["total_pages"],
        body_pages=intermediate.get("body_pages", intermediate["total_pages"]),
        word_count=intermediate["word_count"],
    )

    # Extract case info from cover text and PDF filename
    cover_text = intermediate.get("cover_text", "")
    pdf_path_str = intermediate.get("pdf_path", "")
    case_number, case_title, brief_label = _extract_case_info(cover_text, pdf_path_str)

    report_id = uuid.uuid4().hex[:12]
    report = ComplianceReport(
        brief_type=brief_type,
        recommendation=recommendation,
        results=all_results,
        metadata=metadata,
        claude_reasoning=reasoning,
        report_id=report_id,
        case_number=case_number,
        case_title=case_title,
        brief_label=brief_label,
        pdf_filename=Path(pdf_path_str).name,
    )

    html = build_html_report(report, version_stamp=get_version_stamp())

    output_dir = Path(args.output_dir) if args.output_dir else intermediate_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_stem = Path(intermediate["pdf_path"]).stem
    report_filename = f"compliance-{pdf_stem}-{report_id}.html"
    report_path = output_dir / report_filename
    report_path.write_text(html, encoding="utf-8")

    print(f"Report saved: {report_path}", file=sys.stderr)

    # Print JSON summary to stdout
    summary = {
        "report_id": report_id,
        "report_path": str(report_path),
        "pdf_path": intermediate["pdf_path"],
        "brief_type": brief_type.value,
        "recommendation": recommendation.value,
        "total_checks": len(all_results),
        "failed_checks": len(report.failed_checks),
        "passed_checks": len(report.passed_checks),
        "reasoning": reasoning,
        "failures": [
            {
                "check_id": r.check_id,
                "name": r.name,
                "rule": r.rule,
                "severity": r.severity.value,
                "message": r.message,
            }
            for r in report.failed_checks
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
