#!/usr/bin/env python3
"""CLI wrapper for the appellate brief compliance checker.

Usage:
    python check_brief.py <path-to-pdf> [--brief-type TYPE] [--output-dir DIR]

Extracts the PDF, scans it for concealed text, classifies the brief, runs the
mechanical checks, and writes the intermediate JSON. The semantic checks are
evaluated by Claude in the skill session (see SKILL.md), and build_report.py
merges both into the HTML report. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Derive project root from script location (works from repo or symlinked skill dir)
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from core.brief_classifier import classify_brief
from core.checks_mechanical import run_mechanical_checks
from core.hidden_text import redact_concealed, scan_pdf
from core.models import BriefType
from core.pdf_extract import extract_brief
from core.version_check import get_version_warnings
from check_update import check_for_update


def main():
    parser = argparse.ArgumentParser(description="Check appellate brief PDF for compliance.")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--brief-type", default="auto",
                        choices=["auto", "appellant", "appellee", "reply", "cross_appeal", "amicus",
                                 "amicus_rehearing", "petition_rehearing"],
                        help="Brief type (default: auto-detect)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for output files (default: same as PDF)")
    # Accepted for compatibility with earlier SKILL.md instructions; this is
    # now the only mode.
    parser.add_argument("--mechanical-only", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--skip-version-check", action="store_true",
                        help="Skip remote version check")
    args = parser.parse_args()

    # Update check (cached, weekly)
    update_msg = check_for_update()
    if update_msg:
        print(f"Note: {update_msg}", file=sys.stderr)

    # Rule freshness warnings
    warnings = get_version_warnings(check_remote=not args.skip_version_check)
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract
    print("Extracting PDF metadata...", file=sys.stderr)
    metadata = extract_brief(pdf_path)

    # Scan for concealed content before any of this document's text is used.
    # Order matters: extraction returns invisible text exactly as it returns
    # visible text, so a white-on-white payload is indistinguishable downstream
    # unless it is identified here first.
    print("Scanning for concealed text...", file=sys.stderr)
    hidden_review = scan_pdf(pdf_path)
    hidden_path = output_dir / f"{pdf_path.stem}-hiddentext.json"
    hidden_path.write_text(
        json.dumps(hidden_review.to_dict(), indent=2), encoding="utf-8")
    if hidden_review.spans:
        print(f"NOTICE: {len(hidden_review.spans)} concealed passage(s) found on "
              f"page(s) {', '.join(str(p) for p in hidden_review.pages_affected if p)}. "
              f"Details: {hidden_path}", file=sys.stderr)

    # Remove concealed passages from the text the later passes read, so the
    # analysis sees the document a person sees.  The count is reported; the
    # removed text stays in the sidecar above.
    metadata.full_text, redacted_count = redact_concealed(
        metadata.full_text, hidden_review)
    metadata.cover_text, _ = redact_concealed(metadata.cover_text, hidden_review)
    if redacted_count:
        print(f"Removed {redacted_count} concealed passage(s) from the extracted "
              f"text used for analysis.", file=sys.stderr)

    # Classify
    if args.brief_type != "auto":
        metadata.brief_type = BriefType(args.brief_type)
    else:
        metadata.brief_type = classify_brief(metadata)
    print(f"Brief type: {metadata.brief_type.value}", file=sys.stderr)

    # Mechanical checks
    print("Running mechanical checks...", file=sys.stderr)
    mech_results = run_mechanical_checks(metadata)

    # Intermediate JSON: the skill's semantic pass and build_report.py read this
    intermediate = {
        "pdf_path": str(pdf_path),
        "brief_type": metadata.brief_type.value,
        "total_pages": metadata.total_pages,
        "body_pages": metadata.body_pages,
        "word_count": metadata.word_count,
        "cover_text": metadata.cover_text,
        "full_text": metadata.full_text,
        # Redacted by design: locations and sizes, never the concealed text
        # itself.  Concealed text is routinely an instruction addressed to
        # whatever reads the document, and this file is read by the model
        # that writes the analysis.  The text is in the sidecar, which is
        # for the HTML report and for people.
        "hidden_text": hidden_review.summary_dict(),
        "hidden_text_path": str(hidden_path),
        "hidden_text_redacted_from_full_text": redacted_count,
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


if __name__ == "__main__":
    main()
