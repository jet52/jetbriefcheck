#!/usr/bin/env python3
"""CLI wrapper for the appellate brief compliance checker.

Usage:
    # Full pipeline (API-based semantic checks + report):
    python check_brief.py <path-to-pdf> [--brief-type TYPE] [--output-dir DIR] [--no-semantic]

    # Mechanical-only mode (no API calls, outputs intermediate JSON):
    python check_brief.py <path-to-pdf> --mechanical-only [--brief-type TYPE] [--output-dir DIR]

Imports the core engine from the web app project and runs the analysis pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Derive project root from script location (works from repo or symlinked skill dir)
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from core.brief_classifier import classify_brief
from core.checks_mechanical import run_mechanical_checks
from core.models import BriefType
from core.pdf_extract import extract_brief


def main():
    parser = argparse.ArgumentParser(description="Check appellate brief PDF for compliance.")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--brief-type", default="auto",
                        choices=["auto", "appellant", "appellee", "reply", "cross_appeal", "amicus"],
                        help="Brief type (default: auto-detect)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for output files (default: same as PDF)")
    parser.add_argument("--no-semantic", action="store_true",
                        help="Skip semantic (Claude API) checks")
    parser.add_argument("--mechanical-only", action="store_true",
                        help="Run only extraction + mechanical checks; dump intermediate JSON (no API calls)")
    parser.add_argument("--model", default=None,
                        help="Claude model to use (default: from env or claude-sonnet-4-5-20250929)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract
    print("Extracting PDF metadata...", file=sys.stderr)
    metadata = extract_brief(pdf_path)

    # Classify
    if args.brief_type != "auto":
        metadata.brief_type = BriefType(args.brief_type)
    else:
        metadata.brief_type = classify_brief(metadata)
    print(f"Brief type: {metadata.brief_type.value}", file=sys.stderr)

    # Mechanical checks
    print("Running mechanical checks...", file=sys.stderr)
    mech_results = run_mechanical_checks(metadata)

    # --- Mechanical-only mode: dump intermediate JSON and exit ---
    if args.mechanical_only:
        intermediate = {
            "pdf_path": str(pdf_path),
            "brief_type": metadata.brief_type.value,
            "total_pages": metadata.total_pages,
            "body_pages": metadata.body_pages,
            "word_count": metadata.word_count,
            "cover_text": metadata.cover_text,
            "full_text": metadata.full_text,
            "mechanical_results": [
                {
                    "check_id": r.check_id,
                    "name": r.name,
                    "rule": r.rule,
                    "passed": r.passed,
                    "severity": r.severity.value,
                    "message": r.message,
                    "details": r.details,
                    "applicable": r.applicable,
                }
                for r in mech_results
            ],
        }
        out_path = output_dir / f"{pdf_path.stem}-intermediate.json"
        out_path.write_text(json.dumps(intermediate, indent=2), encoding="utf-8")
        print(f"Intermediate JSON saved: {out_path}", file=sys.stderr)
        # Print the path to stdout so the caller can capture it
        print(str(out_path))
        return

    # --- Full pipeline (original behavior) ---
    # These imports require anthropic SDK; deferred so --mechanical-only works without it
    from core.checks_semantic import run_semantic_checks
    from core.models import ComplianceReport
    from core.recommender import compute_recommendation
    from core.report_builder import build_html_report

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = args.model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

    # Semantic checks
    sem_results = []
    if not args.no_semantic:
        if not api_key:
            print("Warning: ANTHROPIC_API_KEY not set; skipping semantic checks.", file=sys.stderr)
        else:
            print("Running semantic checks (Claude API)...", file=sys.stderr)
            sem_results = run_semantic_checks(metadata, api_key=api_key, model=model)

    all_results = mech_results + sem_results

    # Recommendation
    print("Computing recommendation...", file=sys.stderr)
    use_claude = bool(api_key) and not args.no_semantic
    recommendation, reasoning = compute_recommendation(
        all_results, api_key=api_key, model=model, use_claude_weighting=use_claude,
    )

    # Build report
    import uuid
    report = ComplianceReport(
        brief_type=metadata.brief_type,
        recommendation=recommendation,
        results=all_results,
        metadata=metadata,
        claude_reasoning=reasoning,
        report_id=uuid.uuid4().hex[:12],
    )

    html = build_html_report(report)
    pdf_stem = pdf_path.stem
    report_filename = f"compliance-{pdf_stem}-{report.report_id}.html"
    report_path = output_dir / report_filename
    report_path.write_text(html, encoding="utf-8")
    print(f"Report saved: {report_path}", file=sys.stderr)

    # JSON summary to stdout
    summary = {
        "report_id": report.report_id,
        "report_path": str(report_path),
        "pdf_path": str(pdf_path),
        "brief_type": report.brief_type.value,
        "recommendation": report.recommendation.value,
        "total_checks": len(report.results),
        "failed_checks": len(report.failed_checks),
        "passed_checks": len(report.passed_checks),
        "reasoning": report.claude_reasoning,
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
