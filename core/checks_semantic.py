"""Semantic checks using Claude API for appellate brief compliance.

Sends brief text to Claude to evaluate section presence, adequacy,
and content quality per ND Rules of Appellate Procedure.

Rule text is loaded from bundled files in references/rules/ (relative to
the project root) and included in the prompt so Claude can verify its
citations against the authoritative text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import anthropic

from core.models import BriefMetadata, BriefType, CheckResult, Severity

# Bundled rules directory (relative to project root)
_PROJECT_RULES_DIR = Path(__file__).resolve().parent.parent / "references" / "rules"

# Which rule files are needed for semantic checks
REQUIRED_RULES = [
    "rule-28.md",   # N.D.R.App.P. 28 — Briefs
    "rule-29.md",   # N.D.R.App.P. 29 — Brief of an Amicus Curiae
    "rule-32.md",   # N.D.R.App.P. 32 — Form of Briefs and Other Documents
    "rule-34.md",   # N.D.R.App.P. 34 — Oral Argument
    "rule-30.md",   # N.D.R.App.P. 30 — References to the Record
    "rule-3.4.md",  # N.D.R.Ct. 3.4 — Privacy Protection for Filings
]

# Map of check definitions: (check_id, name, rule, applicable_types, severity, description)
# Citations verified against the actual ND Rules of Appellate Procedure text.
SEMANTIC_CHECKS = [
    # Rule 28(b)(1): "a table of contents, with paragraph references"
    ("SEC-001", "Table of Contents Present", "28(b)(1)",
     None, Severity.REJECT, "Brief must contain a Table of Contents."),
    ("SEC-002", "TOC Uses Paragraph References", "28(b)(1)",
     None, Severity.CORRECTION,
     "Table of Contents must use paragraph references, not page numbers alone."),

    # Rule 28(b)(2): "a table of authorities—cases (alphabetically arranged)...with references to the paragraphs"
    ("SEC-003", "Table of Authorities Present", "28(b)(2)",
     None, Severity.REJECT, "Brief must contain a Table of Authorities."),
    ("SEC-004", "TOA: Cases Alphabetical, Paragraph Refs", "28(b)(2)",
     None, Severity.CORRECTION,
     "Table of Authorities must list cases alphabetically with paragraph references."),

    # Rule 28(b)(3): original jurisdiction statement (not general jurisdictional statement)
    ("SEC-005", "Jurisdictional Statement", "28(b)(3)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "In an original jurisdiction application, appellant must include a jurisdictional statement."),

    # Rule 28(b)(4): "a statement of the issues presented for review"
    ("SEC-006", "Statement of Issues", "28(b)(4)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Statement of the Issues presented for review."),

    # Rule 28(b)(5): "a statement of the case briefly indicating the nature of the case..."
    ("SEC-007", "Statement of the Case", "28(b)(5)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant brief must include a Statement of the Case (procedural history)."),

    # Rule 28(b)(6): "a statement of the facts relevant to the issues...with appropriate references to the record"
    ("SEC-008", "Statement of Facts with Record References", "28(b)(6)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Statement of Facts with record references."),

    # Rule 28(b)(7): "the argument"
    ("SEC-009", "Argument Section Present", "28(b)(7)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.AMICUS], Severity.REJECT,
     "Brief must contain an Argument section."),

    # Rule 28(b)(7)(B)(i): "a concise statement of the applicable standard of review"
    ("SEC-010", "Standard of Review Stated", "28(b)(7)(B)(i)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant must state the applicable standard of review for each issue."),

    # Rule 28(b)(7)(B)(ii): "citation to the record showing that the issue was preserved for review"
    ("SEC-011", "Preservation Citations", "28(b)(7)(B)(ii)",
     [BriefType.APPELLANT], Severity.NOTE,
     "Appellant must cite where each issue was preserved for review in the record."),

    # Rule 28(b)(7)(D): "a short conclusion stating the precise relief sought"
    ("SEC-012", "Conclusion with Precise Relief", "28(b)(7)(D)",
     [BriefType.APPELLANT, BriefType.APPELLEE], Severity.CORRECTION,
     "Brief must include a Conclusion stating the precise relief sought."),

    # Rule 29(a)(4)(C): "a concise statement of the identity of the amicus curiae, and its interest in the case"
    ("SEC-014", "Amicus: Identity/Interest Statement", "29(a)(4)(C)",
     [BriefType.AMICUS], Severity.REJECT,
     "Amicus brief must include a statement of identity and interest."),

    # Rule 29(a)(4)(D): disclosure of authorship and funding
    ("SEC-015", "Amicus: Disclosure Statement", "29(a)(4)(D)",
     [BriefType.AMICUS], Severity.CORRECTION,
     "Amicus brief must include a disclosure statement (authorship and funding)."),

    # Rule 28(e): "counsel should use the parties' actual names or the designations used in the lower court"
    ("CNT-001", "Party References Use Actual Names", "28(e)",
     None, Severity.CORRECTION,
     "Parties should be referred to by actual names, not procedural labels like 'Appellant.'"),

    # Rule 28(l): "must be concise...free from burdensome, irrelevant or immaterial matters"
    ("CNT-002", "Brief Is Concise, No Irrelevant Matter", "28(l)",
     None, Severity.NOTE,
     "Brief must be concise and free of irrelevant, immaterial, or scandalous matter."),

    # Rule 28(g): "the relevant parts must be set out in the brief or in an addendum"
    ("CNT-003", "Statutes/Rules in Brief or Addendum", "28(g)",
     None, Severity.NOTE,
     "Pertinent statutes and rules must be set forth in the brief or addendum."),

    # Rule 30(b)(1): record citations should use (R{index}:{page}) format
    ("REC-002", "Record Citation Format", "30(b)(1)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL], Severity.CORRECTION,
     "Record citations should use the (R{index}:{page}) format per Rule 30(b)(1)."),

    # Rule 30(a): record references should identify the item cited
    ("REC-003", "Record Citations Identify Items", "30(a)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL], Severity.NOTE,
     "Record references should include information identifying the item cited, e.g. 'Statement of John Doe.'"),
]


def _find_rule_file(filename: str) -> Path | None:
    """Find a rule file in the bundled rules directory."""
    candidate = _PROJECT_RULES_DIR / filename
    if candidate.exists():
        return candidate
    return None


def _load_rules_text() -> str:
    """Load rule text from bundled files (shipped with the skill/project).

    Checks the skill directory first, then the project's references/rules/.
    If a rule file is not found, includes a placeholder noting the gap.
    """
    parts = []
    for filename in REQUIRED_RULES:
        filepath = _find_rule_file(filename)
        if filepath is not None:
            parts.append(filepath.read_text(encoding="utf-8"))
        else:
            rule_num = filename.replace("rule-", "").replace(".md", "")
            parts.append(
                f"[Rule {rule_num} text not available. "
                f"Expected at {_PROJECT_RULES_DIR / filename}]"
            )
    return "\n\n---\n\n".join(parts)


def run_semantic_checks(
    metadata: BriefMetadata,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
) -> list[CheckResult]:
    """Run semantic checks via Claude API.

    Sends the brief text, the actual rule text, and check definitions
    in a single API call. The prompt instructs Claude to verify all
    citations against the provided rule text.
    """
    # Filter checks applicable to this brief type
    applicable = []
    inapplicable = []
    for check_id, name, rule, types, severity, desc in SEMANTIC_CHECKS:
        if types is not None and metadata.brief_type not in types:
            inapplicable.append(CheckResult(
                check_id=check_id, name=name, rule=rule,
                passed=True, severity=severity,
                message=f"Not applicable to {metadata.brief_type.value} briefs.",
                applicable=False,
            ))
        else:
            applicable.append((check_id, name, rule, severity, desc))

    if not applicable:
        return inapplicable

    # Build the prompt
    checks_json = json.dumps([
        {"id": cid, "name": name, "rule": rule, "description": desc}
        for cid, name, rule, _, desc in applicable
    ], indent=2)

    # Load the actual rule text
    rules_text = _load_rules_text()

    # Truncate brief text if very long (keep first ~60k chars to leave room for rules)
    brief_text = metadata.full_text
    if len(brief_text) > 60000:
        brief_text = brief_text[:60000] + "\n\n[TEXT TRUNCATED]"

    prompt = f"""You are a legal compliance reviewer for the North Dakota Supreme Court.
Analyze the following appellate brief for compliance with the ND Rules of Appellate Procedure.

Brief type: {metadata.brief_type.value}
Total pages: {metadata.total_pages}
Word count: {metadata.word_count}

IMPORTANT: The authoritative rule text is provided below. You MUST use it to verify every
rule citation in your response. Do NOT guess or invent subdivision numbers. If a check's
rule citation does not match what you find in the rule text, use the correct citation from
the rule text and note the discrepancy.

<rules>
{rules_text}
</rules>

The brief text follows:

<brief>
{brief_text}
</brief>

Evaluate each of the following checks. For each check, determine whether the brief passes
or fails, provide a brief explanation, and verify that the rule citation is correct by
cross-referencing the rule text above.

Checks to evaluate:
{checks_json}

Return ONLY a JSON array with objects having these fields:
- "id": the check ID
- "passed": true or false
- "rule": the correct rule citation (verify against the rule text above — use the exact
  subdivision numbering from the rule text, e.g. "28(b)(1)" not "28(a)(1)")
- "message": a one-sentence explanation of the finding
- "details": optional additional detail (null if none)

Evaluation guidance:
- SEC-001: Rule 28(b)(1) requires "a table of contents, with paragraph references."
  Look for a Table of Contents section.
- SEC-002: Rule 28(b)(1) requires the TOC to use "paragraph references" — check whether
  the TOC references paragraph numbers (¶ or [1], [2], etc.) rather than only page numbers.
- SEC-003: Rule 28(b)(2) requires "a table of authorities—cases (alphabetically arranged),
  statutes, and other authorities—with references to the paragraphs in the brief."
- SEC-004: Check if cases in the TOA are alphabetical and use paragraph references per 28(b)(2).
- SEC-005: Rule 28(b)(3) applies only to original jurisdiction applications. If this is a
  standard appeal (not original jurisdiction), it passes automatically.
- SEC-006: Rule 28(b)(4) requires "a statement of the issues presented for review."
- SEC-007: Rule 28(b)(5) requires "a statement of the case briefly indicating the nature
  of the case, the course of the proceedings, and the disposition below."
- SEC-008: Rule 28(b)(6) requires "a statement of the facts relevant to the issues...with
  appropriate references to the record (see Rule 28(f))." Look for record references
  like "App. 15", "Doc. 23", or similar citations to the appendix/record.
- SEC-009: Rule 28(b)(7) requires "the argument." Look for a substantive Argument section.
- SEC-010: Rule 28(b)(7)(B)(i) requires "a concise statement of the applicable standard
  of review" for each issue.
- SEC-011: Rule 28(b)(7)(B)(ii) requires "citation to the record showing that the issue
  was preserved for review; or a statement of grounds for seeking review of an issue not preserved."
- SEC-012: Rule 28(b)(7)(D) requires "a short conclusion stating the precise relief sought."
- SEC-014: Rule 29(a)(4)(C) requires "a concise statement of the identity of the amicus
  curiae, and its interest in the case."
- SEC-015: Rule 29(a)(4)(D) requires a disclosure statement about authorship and funding.
- CNT-001: Rule 28(e) says "counsel should use the parties' actual names or the designations
  used in the lower court." Check if parties are referred to by name rather than "Appellant"/"Appellee."
- CNT-002: Rule 28(l) requires briefs to be "concise...free from burdensome, irrelevant
  or immaterial matters."
- CNT-003: Rule 28(g) requires that if "the court's determination of the issues presented
  requires the study of statutes, rules, regulations, etc., the relevant parts must be set
  out in the brief or in an addendum."
- REC-002: Rule 30(b)(1) requires record citations in the format (R{{index}}:{{page}}), e.g.
  (R156:12). Check whether record references in the brief consistently use this format. Note
  any citations that use other formats (e.g., "App. 15", "Doc. 23", "Tr. 45") instead of the
  required (R#:#) format. If the brief uses a mix of formats, note which are non-compliant.
- REC-003: Rule 30(a) requires that record references include "information identifying the
  item," e.g. "Statement of John Doe." Check whether the brief's record citations provide
  enough context to identify what is being cited, either in the text surrounding the citation
  or in the citation itself. Bare citations like (R12:5) with no surrounding context about
  what the item is should be flagged.

Return ONLY valid JSON, no markdown formatting."""

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=key)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse the response
    response_text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        response_text = "\n".join(lines)

    results = _parse_semantic_response(response_text, applicable)
    results.extend(inapplicable)
    return results


def _parse_semantic_response(
    response_text: str,
    checks: list[tuple],
) -> list[CheckResult]:
    """Parse Claude's JSON response into CheckResult objects.

    If Claude returns a corrected rule citation, use it instead of the default.
    """
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return _fallback_results(checks, "Failed to parse Claude API response as JSON.")
        else:
            return _fallback_results(checks, "Claude API returned non-JSON response.")

    # Build a lookup for check metadata
    check_map = {cid: (name, rule, severity, desc) for cid, name, rule, severity, desc in checks}

    results = []
    seen_ids = set()

    for item in data:
        cid = item.get("id", "")
        if cid not in check_map:
            continue
        seen_ids.add(cid)
        name, default_rule, severity, _ = check_map[cid]

        # Use Claude's corrected rule citation if provided, otherwise use our default
        rule = item.get("rule", default_rule) or default_rule

        results.append(CheckResult(
            check_id=cid,
            name=name,
            rule=rule,
            passed=bool(item.get("passed", True)),
            severity=severity,
            message=item.get("message", "No details provided."),
            details=item.get("details"),
        ))

    # Add fallbacks for any checks Claude didn't address
    for cid, name, rule, severity, desc in checks:
        if cid not in seen_ids:
            results.append(CheckResult(
                check_id=cid, name=name, rule=rule,
                passed=True, severity=severity,
                message="Not evaluated by AI analysis; manual review recommended.",
            ))

    return results


def _fallback_results(
    checks: list[tuple], error_msg: str
) -> list[CheckResult]:
    """Return inconclusive results when API parsing fails."""
    return [
        CheckResult(
            check_id=cid, name=name, rule=rule,
            passed=True, severity=severity,
            message=f"AI analysis unavailable: {error_msg}",
        )
        for cid, name, rule, severity, _ in checks
    ]
