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
from core.semantic_definitions import (  # noqa: F401
    SEMANTIC_CHECKS,
    gated_check_result,
)

# Bundled rules directory (relative to project root)
_PROJECT_RULES_DIR = Path(__file__).resolve().parent.parent / "references" / "rules"

# Which rule files are needed for semantic checks
REQUIRED_RULES = [
    "rule-28.md",    # N.D.R.App.P. 28 — Briefs
    "rule-29.md",    # N.D.R.App.P. 29 — Brief of an Amicus Curiae
    "rule-32.md",    # N.D.R.App.P. 32 — Form of Briefs and Other Documents
    "rule-34.md",    # N.D.R.App.P. 34 — Oral Argument
    "rule-40.md",    # N.D.R.App.P. 40 — Petition for Rehearing
    "rule-30.md",    # N.D.R.App.P. 30 — References to the Record
    "rule-3.4.md",   # N.D.R.Ct. 3.4 — Privacy Protection for Filings
    "rule-14.md",    # N.D.R.App.P. 14 — Identity Protection
    "rule-21.md",    # N.D.R.App.P. 21 — Writs
    "rule-11.6.md",  # N.D.R.Ct. 11.6 — Medium-Neutral Case Citations
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
            inapplicable.append(gated_check_result(
                check_id, name, rule, severity, metadata.brief_type))
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
- CNT-005: Rule 28(f)(2) provides that "a party may not incorporate by reference the contents
  of a brief filed elsewhere or in another case." Look for language adopting or incorporating
  arguments from a district court brief, a summary judgment memorandum, a brief in another
  appeal or case, or a filing below (e.g., "incorporated herein by reference", "adopts the
  arguments made in its brief to the district court", "for the reasons stated in (R45)").
  Fail if the brief incorporates such material instead of arguing it. Do not fail for
  (1) joining or adopting part of another party's appellate brief in this case, which
  Rule 28(j) permits, (2) an appellant's reply or cross-appeal answer referring to its own
  principal brief in this appeal, which Rule 28(i)(2) permits, or (3) citing a filing below
  as record evidence of what was argued there (e.g., to show preservation).
- REC-002: Rule 30(b)(1) requires record citations in the format (R{{index}}:{{page}}), e.g.
  (R156:12). Check whether record references in the brief consistently use this format. Note
  any citations that use other formats (e.g., "App. 15", "Doc. 23", "Tr. 45") instead of the
  required (R#:#) format. If the brief uses a mix of formats, note which are non-compliant.
- REC-003: Rule 30(a) requires that record references include "information identifying the
  item," e.g. "Statement of John Doe." Check whether the brief's record citations provide
  enough context to identify what is being cited, either in the text surrounding the citation
  or in the citation itself. Bare citations like (R12:5) with no surrounding context about
  what the item is should be flagged.
- PRV-001: N.D.R.Ct. 3.4(b)(1)(C) requires that "the name of an individual known to be a
  minor" be redacted to the minor's initials; Rule 14(a)(5) imposes the same obligation.
  Check whether any minor's full first or last name appears in the brief text. Minors should
  be identified by initials throughout (e.g. "H.R.", with or without periods). The most
  common failure is inconsistency: initials in most places, with the actual name slipping
  into quoted testimony or narrative. Do not flag the cover-page party caption, where a
  parent's name naturally appears. Rule 3.4(b)(3)(E) exempts minors who are parties in
  certain case types (traffic, name change, conservatorship, protection orders); in a
  standard custody or family-law appeal the children are not parties and the exemption does
  not apply, so initials are required. If no minor is involved in the case, pass.
- PRV-002: Rule 14(a)(1) requires that the respondent in a mental health proceeding be
  referred to by initials only. First determine if this is a mental health case (look for
  indicators like "mental health commitment", "treatment order", N.D.C.C. ch. 25-03.1, etc.).
  If not a mental health case, pass automatically. If it is, check whether the respondent's
  full name appears anywhere (it should be initials only). Note: PRV-001 covers minor names
  under N.D.R.Ct. 3.4; this check specifically addresses Rule 14(a)(1) mental health cases.
- PRV-003: Rule 14(a)(2) requires initials for the respondent and family members in
  guardianship/conservatorship proceedings. Determine if this is such a case (look for
  "guardianship", "conservatorship", N.D.C.C. ch. 30.1). If not, pass automatically.
  If it is, check that the respondent and family members use initials only.
- PRV-004: Rule 14(a)(3) requires initials for the respondent in a juvenile proceeding.
  Determine if this is a juvenile case (look for "juvenile", "delinquent", N.D.C.C. ch. 27-20).
  If not, pass automatically. If it is, check that the juvenile respondent uses initials.
- PRV-005: Rule 14(a)(4) requires initials for the child and family members in termination
  of parental rights proceedings. Look for "termination of parental rights", "TPR",
  N.D.C.C. ch. 27-20. If not a TPR case, pass automatically. If it is, check that the
  child and family members use initials only.
- PRV-006: Rule 14(a)(6) requires initials for victims or alleged victims of sexual offenses.
  Determine if the case involves a sexual offense (look for sexual assault, rape, gross sexual
  imposition, N.D.C.C. ch. 12.1-20, etc.). If not, pass automatically. If it is, check that
  the victim is referred to by initials only.
- WRT-001: Rule 21(a)(2) requires a writ petition to state: (A) relief sought, (B) issues
  presented, (C) facts necessary to understand the issues, and (D) reasons why a writ should
  issue. First determine if this is a writ petition (look for "supervisory writ", "writ of
  mandamus", "writ of prohibition", "extraordinary writ", "petition for writ"). If not a
  writ petition, pass automatically. If it is, check that all four elements are present.
- WRT-002: Rule 21(a)(3) requires a writ petition to be accompanied by any document necessary
  to understand it that is not in the record of a related district court proceeding (order,
  opinion, brief, declaration). Those documents must be attached as exhibits (21(a)(3)(B));
  documents already in a related district court record must not be refiled and are cited under
  Rule 30 (21(a)(3)(C)). If not a writ petition, pass automatically. If it is, check that the
  documents the petition relies on are attached as exhibits or cited to the related record.
- WRT-003: Rule 21(a)(3)(B) requires exhibits to be cited as (E{{exhibit number}}:{{page within
  exhibit}}), e.g. (E6:12), with paragraph or line numbers after the page if applicable, e.g.
  (E6:12:¶3). Rule 21(a)(3)(D) requires the first reference to each exhibit to name the
  document, e.g. "Order Denying Motion to Suppress (E6:12)". Rule 30(b)(1) bars "Id." for
  exhibit citations. If not a writ petition, pass automatically. If it is, fail when exhibit
  citations do not follow this format, are left as placeholders, or first references do not
  identify the document.
- RHR-001: Rule 40(a)(2) requires the petition to "state with particularity each point of law
  or fact that the petitioner believes the court has overlooked or misapprehended." Look for
  specific identification of points the court allegedly overlooked or misunderstood. The petition
  should not merely reargue the case — it must identify particular points. If the petition is not
  a petition for rehearing, pass automatically.
- RHR-002: Rule 40(b) requires the petition to "include items required under Rule 28(b) that
  are applicable." For a rehearing petition, the most commonly applicable items are a table of
  contents (28(b)(1)) and table of authorities (28(b)(2)). Check whether the petition includes
  these sections. A very short petition (a few pages) may reasonably omit a TOC/TOA. If the
  petition is not a petition for rehearing, pass automatically.
- RHR-003: Rule 40(a)(2) requires the petition to "contain such argument in support of the
  petition as the petitioner desires to present." Look for a substantive argument section that
  supports the claim that the court overlooked or misapprehended specific points. If the petition
  is not a petition for rehearing, pass automatically.
- CIT-002: N.D.R.Ct. 11.6 distinguishes pre-1997 and post-1997 ND Supreme Court opinions.
  Post-1997 opinions must include the medium-neutral citation (YYYY ND ##). Pre-1997
  opinions need only the N.W.2d citation. Check whether the brief correctly applies this
  distinction — e.g., a case from 2005 should have "2005 ND 123" format, while a case from
  1990 needs only the N.W.2d cite. Be lenient; this is an advisory check.

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

    # Any check the model did not address was not evaluated.  Reporting it as
    # passed would put it in the report's "Passed Checks" list and let it
    # support an ACCEPT — asserting compliance that was never assessed.  Mark
    # it undetermined instead, so it lands in "Not Applicable / Not
    # Determined" and cannot move the recommendation.
    for cid, name, rule, severity, desc in checks:
        if cid not in seen_ids:
            results.append(CheckResult(
                check_id=cid, name=name, rule=rule,
                passed=False, severity=severity, applicable=False,
                message="Not evaluated by AI analysis; requires manual review.",
                details="This check was sent for analysis but no result came "
                        "back for it. It has not been verified either way.",
            ))

    return results


def _fallback_results(
    checks: list[tuple], error_msg: str
) -> list[CheckResult]:
    """Return undetermined results when the API call or its parsing fails.

    This path fires for every semantic check at once, so marking them passed
    would produce a report whose "Passed Checks" list is entirely fictional
    and whose recommendation could be ACCEPT on the strength of an analysis
    that never ran.  They are undetermined (``applicable=False``): excluded
    from both the passed and the failed tallies, and unable to move the
    recommendation.
    """
    return [
        CheckResult(
            check_id=cid, name=name, rule=rule,
            passed=False, severity=severity, applicable=False,
            message=f"Not determined — AI analysis unavailable: {error_msg}",
            details="No semantic check was evaluated. Nothing in this "
                    "section has been verified; review the brief manually.",
        )
        for cid, name, rule, severity, _ in checks
    ]
