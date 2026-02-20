---
name: brief-compliance
version: 1.3.0
description: >-
  Triggers when a user uploads a legal brief PDF for compliance review against the
  North Dakota Rules of Appellate Procedure. Analyzes the brief and produces an HTML
  compliance report with a recommended action (Accept, Correction Letter, or Reject).
triggers:
  - brief compliance
  - check brief
  - compliance check
  - check appellate brief
  - appellate brief
  - legal brief review
  - brief PDF
  - ND rules compliance
---

# Appellate Brief Compliance Checker

## What This Skill Does

Analyzes an appellate brief PDF against the North Dakota Rules of Appellate Procedure and produces a detailed HTML compliance report. The report includes:

- **Recommendation**: Accept, Correction Letter, or Reject
- **Mechanical checks**: Paper size, margins, font size, spacing, page limits, page numbering, cover requirements
- **Semantic checks** (evaluated by Claude): Section presence and adequacy (TOC, TOA, Statement of Issues, Argument, etc.), party naming conventions, conciseness

## Setup

Install the required dependency before running scripts:

```bash
pip install PyMuPDF
```

## Workflow (Three Phases)

The user uploads a PDF via drag-and-drop. Save the uploaded file to a temporary location, then execute these three phases in order.

### Phase 0: Save the Uploaded PDF

The user will drag-and-drop a PDF into the chat. Save the uploaded file to a working directory so the scripts can access it:

```python
# Example: write the uploaded PDF bytes to a temp path
import shutil
shutil.copy("<uploaded-file-path>", "/tmp/brief.pdf")
```

Use `/tmp/` as the working directory for all intermediate and output files.

### Phase 1: Extract + Mechanical Checks (Script)

Run the check script in mechanical-only mode — this makes **no API calls**:

```bash
python scripts/check_brief.py "/tmp/brief.pdf" --mechanical-only [--brief-type auto|appellant|appellee|reply|cross_appeal|amicus] [--output-dir /tmp]
```

The script outputs an intermediate JSON file path to stdout. Capture this path.

### Phase 2: Semantic Analysis (Claude)

You (Claude) perform the semantic analysis directly — no API call needed.

1. **Read the intermediate JSON** from Phase 1 to get `brief_type`, `full_text`, `cover_text`, and `mechanical_results`.

2. **Read the rule files** for reference (bundled with the skill):
   - `references/rules/rule-28.md` — N.D.R.App.P. 28 (Briefs)
   - `references/rules/rule-29.md` — N.D.R.App.P. 29 (Amicus Curiae)
   - `references/rules/rule-32.md` — N.D.R.App.P. 32 (Form of Briefs)
   - `references/rules/rule-30.md` — N.D.R.App.P. 30 (References to the Record)
   - `references/rules/rule-34.md` — N.D.R.App.P. 34 (Oral Argument)
   - `references/rules/rule-3.4.md` — N.D.R.Ct. 3.4 (Privacy Protection)

3. **Read the check definitions** at `references/check-definitions.md` — the "Semantic Checks" section contains detailed evaluation guidance for each check ID.

4. **Evaluate each applicable semantic check** against the brief text, following the evaluation guidance in check-definitions.md. Filter by brief type first (see "Applicability by Brief Type" in check-definitions.md).

5. **Write the semantic results** to a JSON file at `<output-dir>/<pdf-stem>-semantic.json` (same directory as the intermediate JSON). Use this exact schema:

```json
{
  "semantic_results": [
    {
      "check_id": "SEC-001",
      "name": "Table of Contents Present",
      "rule": "28(b)(1)",
      "passed": true,
      "severity": "reject",
      "message": "Table of Contents is present beginning on page 2.",
      "details": null,
      "applicable": true
    }
  ]
}
```

Each semantic check must appear in the results — either as an evaluated result (applicable: true) or as not-applicable (passed: true, applicable: false).

The severity values must be lowercase: `"reject"`, `"correction"`, or `"note"`.

### Phase 3: Build Report (Script)

Run the report builder to merge results and generate the HTML report:

```bash
python scripts/build_report.py \
  --intermediate "<intermediate-json-path>" \
  --semantic "<semantic-json-path>" \
  [--output-dir /tmp]
```

The script will:
1. Load mechanical results from the intermediate JSON
2. Load semantic results from the semantic JSON
3. Merge into a single results list
4. Compute a recommendation using hard-rule logic (no API call)
5. Generate an HTML report
6. Print a JSON summary to stdout

### Phase 4: Report to User

After Phase 3, report the findings to the user:
- State the **recommendation** (Accept, Correction Letter, or Reject)
- Summarize any **failed checks** grouped by severity
- Provide the generated HTML report as a downloadable file

## Output

- An HTML compliance report file
- A JSON summary printed to stdout with the recommendation and failed checks

## Requirements

- Python with PyMuPDF installed: `pip install PyMuPDF`
- No API keys needed — semantic analysis is performed by Claude directly

## Known Issues

Based on testing across 13 briefs (Feb 2026):

### Mechanical Check False Positives

Three mechanical checks have high false-positive rates. When reporting results, note these caveats to the user:

- **FMT-006 (Font Size)**: Measures the minimum font found anywhere in the PDF. Small fonts in page numbers, headers, footers, superscripts, or PDF artifacts trigger REJECT even when the body text is properly 12pt. If this is the sole REJECT trigger and the reported minimum is 8-11pt, flag it as a likely false positive.
- **FMT-009 (Spacing)**: Nearly all briefs are flagged as single-spaced. The detector is miscalibrated for many PDF encodings. If the brief appears to be a standard attorney-prepared document, note this is likely a false positive.
- **FMT-005 (Bottom Margin)**: Page numbers at the bottom are measured as content in the margin zone. Nearly always triggers.

### Brief Type Auto-Detection

The `--brief-type auto` flag frequently returns "unknown", especially for appellee briefs. If auto-detection fails, re-run Phase 1 with an explicit `--brief-type` flag based on the cover page text.

### Detection Variants

- **COV-002 (Oral Argument)**: Misses "REQUEST FOR ORAL ARGUMENT" — only matches "ORAL ARGUMENT REQUESTED".
- **SEC-013 (Certificate of Compliance)**: Misses "CERTIFICATION OF COMPLIANCE" variant.

### Non-Appellate Briefs

The test corpus may include non-appellate briefs (e.g., "Brief in Support of Motion"). These are not subject to Rules 28/32 and should be skipped. Check the cover page and brief content before proceeding.

## References

- [Rules Summary](references/rules-summary.md) — Condensed ND Rules of Appellate Procedure
- [Check Definitions](references/check-definitions.md) — Full catalog of checks with IDs, severities, and semantic evaluation guidance
- [Bundled Rules](references/rules/) — Full text of N.D.R.App.P. 28, 29, 30, 32, 34 and N.D.R.Ct. 3.4
