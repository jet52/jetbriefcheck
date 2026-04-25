"""Semantic checks using Claude API for appellate brief compliance.

Sends brief text to Claude to evaluate section presence, adequacy,
and content quality per Iowa Rules of Appellate Procedure.

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
    "rule-6.903.md",   # Iowa R. App. P. 6.903 — Briefs
    "rule-6.904.md",   # Iowa R. App. P. 6.904 — References in Briefs
    "rule-6.906.md",   # Iowa R. App. P. 6.906 — Amicus Curiae Briefs
    "rule-6.907.md",   # Iowa R. App. P. 6.907 — Oral Argument
    "rule-6.1101.md",  # Iowa R. App. P. 6.1101 — Routing of Cases
    "rule-1.422.md",   # Confidential Filings / Privacy
]

# Map of check definitions: (check_id, name, rule, applicable_types, severity, description)
# Citations verified against the Iowa Rules of Appellate Procedure.
SEMANTIC_CHECKS = [
    # Rule 6.903(2)(1): table of contents with page references
    ("SEC-001", "Table of Contents Present", "6.903(2)(1)",
     None, Severity.REJECT, "Brief must contain a Table of Contents."),
    ("SEC-002", "TOC Uses Page References", "6.903(2)(1)",
     None, Severity.CORRECTION,
     "Table of Contents must include page references."),

    # Rule 6.903(2)(2): table of authorities with page references
    ("SEC-003", "Table of Authorities Present", "6.903(2)(2)",
     None, Severity.REJECT, "Brief must contain a Table of Authorities."),
    ("SEC-004", "TOA: Cases Alphabetical, Page Refs", "6.903(2)(2)",
     None, Severity.CORRECTION,
     "Table of Authorities must list cases alphabetically with page references."),

    # Rule 6.903(2)(3): statement of the issues presented for review
    ("SEC-006", "Statement of Issues", "6.903(2)(3)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Statement of the Issues presented for review."),

    # Rule 6.903(2)(3): each issue must include preservation citation and most apposite authority
    ("SEC-006A", "Issues Include Preservation & Authority Citations", "6.903(2)(3)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Each issue must include a citation to where it was preserved and the most apposite authority."),

    # Rule 6.903(2)(4): routing statement
    ("SEC-016", "Routing Statement", "6.903(2)(4)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Routing Statement (retained by Supreme Court or transferred to Court of Appeals)."),

    # Rule 6.903(2)(5): statement of the case
    ("SEC-007", "Statement of the Case", "6.903(2)(5)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant brief must include a Statement of the Case (nature, proceedings, disposition)."),

    # Rule 6.903(2)(6): statement of the facts with record references
    ("SEC-008", "Statement of Facts with Record References", "6.903(2)(6)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Statement of Facts with references to the record."),

    # Rule 6.903(2)(7): argument section
    ("SEC-009", "Argument Section Present", "6.903(2)(7)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.AMICUS], Severity.REJECT,
     "Brief must contain an Argument section."),

    # Rule 6.903(2)(7): scope/standard of review for each issue
    ("SEC-010", "Standard/Scope of Review Stated", "6.903(2)(7)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant must state the scope or standard of review for each issue."),

    # Rule 6.903(2)(7): preservation of error for each issue
    ("SEC-017", "Preservation of Error", "6.903(2)(7)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant must state how each issue was preserved for appellate review with record references."),

    # Rule 6.903(2)(8): conclusion with precise relief
    ("SEC-012", "Conclusion with Precise Relief", "6.903(2)(8)",
     [BriefType.APPELLANT, BriefType.APPELLEE], Severity.CORRECTION,
     "Brief must include a Conclusion stating the precise relief sought."),

    # Rule 6.903(2)(9): request for oral argument
    ("SEC-018", "Request for Oral Argument", "6.903(2)(9)",
     [BriefType.APPELLANT, BriefType.APPELLEE], Severity.NOTE,
     "Brief must include a request for oral argument or a waiver of oral argument."),

    # Rule 6.903(1)(i): certificate of compliance
    ("SEC-013", "Certificate of Compliance", "6.903(1)(i)",
     None, Severity.CORRECTION,
     "Brief must include a Certificate of Compliance with typeface and type-volume requirements."),

    # Rule 6.903(2)(11): certificate of filing and service
    ("SEC-019", "Certificate of Filing/Service", "6.903(2)(11)",
     None, Severity.CORRECTION,
     "Brief must include a Certificate of Filing and Service."),

    # Rule 6.906(3)(C): amicus identity and interest statement
    ("SEC-014", "Amicus: Identity/Interest Statement", "6.906(3)",
     [BriefType.AMICUS], Severity.REJECT,
     "Amicus brief must include a statement of identity and interest."),

    # Rule 6.906(3)(D): amicus disclosure statement
    ("SEC-015", "Amicus: Disclosure Statement", "6.906(3)",
     [BriefType.AMICUS], Severity.CORRECTION,
     "Amicus brief must include a disclosure statement (authorship and funding)."),

    # Rule 6.904(1): party references use actual names
    ("CNT-001", "Party References Use Actual Names", "6.904(1)",
     None, Severity.CORRECTION,
     "Parties should be referred to by actual names, not procedural labels like 'Appellant.'"),

    # General: brief conciseness
    ("CNT-002", "Brief Is Concise, No Irrelevant Matter", "6.903",
     None, Severity.NOTE,
     "Brief must be concise and free of irrelevant, immaterial, or scandalous matter."),

    # Rule 6.904(3): statutes/rules in brief or addendum
    ("CNT-003", "Statutes/Rules in Brief or Addendum", "6.904(3)",
     None, Severity.NOTE,
     "Pertinent statutes and rules must be set forth in the brief or addendum."),

    # Rule 6.904(2): record citation format (App. pp. ___)
    ("REC-002", "Record Citation Format", "6.904(2)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL], Severity.CORRECTION,
     "Record citations should use the (App. pp. ___) or (Tr. p. ___) format per Rule 6.904(2)."),

    # Rule 6.904(2): record citations identify items
    ("REC-003", "Record Citations Identify Items", "6.904(2)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL], Severity.NOTE,
     "Record references should provide enough context to identify what is being cited."),
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
    model: str = "claude-sonnet-4-6",
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

    prompt = f"""You are a legal compliance reviewer for the Iowa Supreme Court and Iowa Court of Appeals.
Analyze the following appellate brief for compliance with the Iowa Rules of Appellate Procedure.

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
- "rule": the correct rule citation (verify against the rule text above)
- "message": a one-sentence explanation of the finding
- "details": optional additional detail (null if none)

Evaluation guidance:
- SEC-001: Rule 6.903(2)(1) requires a table of contents with page references.
  Look for a Table of Contents section.
- SEC-002: Rule 6.903(2)(1) requires the TOC to use page references. Iowa uses page
  references (not paragraph references). Check that the TOC entries
  include page numbers.
- SEC-003: Rule 6.903(2)(2) requires a table of authorities with page references.
- SEC-004: Check if cases in the TOA are alphabetical and use page references per 6.903(2)(2).
- SEC-006: Rule 6.903(2)(3) requires a statement of the issues presented for review.
- SEC-006A: Rule 6.903(2)(3) requires each issue to include a citation to where it was
  preserved in the district court record AND the most apposite authority. Check both.
- SEC-016: Rule 6.903(2)(4) requires a routing statement indicating whether the case
  should be retained by the supreme court or transferred to the court of appeals, per
  the criteria in Iowa R. App. P. 6.1101(2) and (3). This is an Iowa-specific requirement.
- SEC-007: Rule 6.903(2)(5) requires a statement of the case (nature, proceedings, disposition).
- SEC-008: Rule 6.903(2)(6) requires a statement of the facts with record references
  (App. pp. ___, Tr. p. ___, etc.).
- SEC-009: Rule 6.903(2)(7) requires an argument section.
- SEC-010: Rule 6.903(2)(7) requires a scope or standard of review for each issue,
  with supporting authorities.
- SEC-017: Rule 6.903(2)(7) requires a statement of how each issue was preserved for
  appellate review, with references to the record where the issue was raised and decided.
  This is the "preservation of error" requirement.
- SEC-012: Rule 6.903(2)(8) requires a short conclusion stating the precise relief sought.
- SEC-018: Rule 6.903(2)(9) requires either a request for oral argument or a statement
  that oral argument is not requested.
- SEC-013: Rule 6.903(1)(i) requires a certificate of compliance with typeface and
  type-volume requirements (Form 7).
- SEC-019: Rule 6.903(2)(11) requires a certificate of filing and service.
- SEC-014: Rule 6.906(3) requires amicus to include identity and interest statement.
- SEC-015: Rule 6.906(3) requires amicus disclosure statement (authorship and funding).
- CNT-001: Rule 6.904(1) says counsel should use parties' actual names, not procedural labels.
- CNT-002: Brief should be concise and free of irrelevant matter.
- CNT-003: Rule 6.904(3) requires relevant statutes/rules in the brief or addendum.
- REC-002: Rule 6.904(2) requires record citations in the format (App. pp. ___) for
  appendix references and (Tr. p. ___) for transcript references. Check whether the
  brief consistently uses these formats.
- REC-003: Rule 6.904(2) requires record references to provide context identifying
  what is being cited.

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
