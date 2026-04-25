"""Flask routes for the brief compliance checker."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from core.brief_classifier import classify_brief
from core.checks_mechanical import run_mechanical_checks
from core.checks_semantic import run_semantic_checks
from core.models import BriefType, ComplianceReport
from core.pdf_extract import extract_brief
from core.recommender import compute_recommendation
from core.report_builder import build_html_report

bp = Blueprint("main", __name__)

# In-memory report storage (no database for v1)
reports: dict[str, tuple[ComplianceReport, str]] = {}  # id -> (report, html)


@bp.route("/")
def index():
    return render_template("upload.html")


@bp.route("/analyze", methods=["POST"])
def analyze():
    """Handle PDF upload, run analysis, redirect to report."""
    if "pdf" not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for("main.index"))

    file = request.files["pdf"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("main.index"))

    if not file.filename.lower().endswith(".pdf"):
        flash("Please upload a PDF file.", "error")
        return redirect(url_for("main.index"))

    # Save uploaded file
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(upload_dir, f"{uuid.uuid4().hex}_{filename}")
    file.save(filepath)

    try:
        report = _run_analysis(filepath, request.form.get("brief_type"))
        report_id = uuid.uuid4().hex[:12]
        report.report_id = report_id
        html = build_html_report(report)
        reports[report_id] = (report, html)
        return redirect(url_for("main.report", report_id=report_id))
    except Exception as e:
        flash(f"Analysis failed: {e}", "error")
        return redirect(url_for("main.index"))
    finally:
        # Clean up uploaded file
        try:
            os.unlink(filepath)
        except OSError:
            pass


@bp.route("/report/<report_id>")
def report(report_id: str):
    """Display a compliance report."""
    entry = reports.get(report_id)
    if entry is None:
        flash("Report not found.", "error")
        return redirect(url_for("main.index"))
    _, html = entry
    return html


@bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    """JSON API for brief analysis."""
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF file provided."}), 400

    file = request.files["pdf"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF."}), 400

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(upload_dir, f"{uuid.uuid4().hex}_{filename}")
    file.save(filepath)

    try:
        report = _run_analysis(filepath, request.form.get("brief_type"))
        report_id = uuid.uuid4().hex[:12]
        report.report_id = report_id
        html = build_html_report(report)
        reports[report_id] = (report, html)

        return jsonify({
            "report_id": report_id,
            "recommendation": report.recommendation.value,
            "brief_type": report.brief_type.value,
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
                    "details": r.details,
                }
                for r in report.failed_checks
            ],
            "report_url": url_for("main.report", report_id=report_id, _external=True),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(filepath)
        except OSError:
            pass


def _run_analysis(filepath: str, brief_type_override: str | None = None) -> ComplianceReport:
    """Run the full analysis pipeline on a PDF."""
    api_key = current_app.config.get("ANTHROPIC_API_KEY", "")
    model = current_app.config.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Extract PDF metadata
    metadata = extract_brief(filepath)

    # Classify brief type
    if brief_type_override and brief_type_override != "auto":
        try:
            metadata.brief_type = BriefType(brief_type_override)
        except ValueError:
            metadata.brief_type = classify_brief(metadata)
    else:
        metadata.brief_type = classify_brief(metadata)

    # Run mechanical checks
    mech_results = run_mechanical_checks(metadata)

    # Run semantic checks
    sem_results = run_semantic_checks(metadata, api_key=api_key, model=model)

    all_results = mech_results + sem_results

    # Compute recommendation
    recommendation, reasoning = compute_recommendation(
        all_results, api_key=api_key, model=model,
    )

    return ComplianceReport(
        brief_type=metadata.brief_type,
        recommendation=recommendation,
        results=all_results,
        metadata=metadata,
        claude_reasoning=reasoning,
    )
