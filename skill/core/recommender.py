"""Hybrid recommendation engine: hard rules + Claude weighting.

Determines final recommendation (ACCEPT, CORRECTION_LETTER, REJECT)
based on check results, with optional Claude-based borderline adjustment.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import anthropic

from core.models import CheckResult, ComplianceReport, Recommendation, Severity


def compute_recommendation(
    results: list[CheckResult],
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
    use_claude_weighting: bool = True,
) -> tuple[Recommendation, str]:
    """Compute the final recommendation from check results.

    Returns (recommendation, reasoning_text).
    """
    # Step 1: Hard-rule pass
    hard_rec = _hard_rule_pass(results)
    reasoning = ""

    # Step 2: Claude weighting (only if no REJECT failures)
    if use_claude_weighting and hard_rec != Recommendation.REJECT:
        claude_rec, reasoning = _claude_weighting_pass(results, hard_rec, api_key, model)
        # Claude can escalate but never downgrade
        final = max(hard_rec.value, claude_rec.value, key=_rec_rank)
        final = Recommendation(final)
    else:
        final = hard_rec
        if hard_rec == Recommendation.REJECT:
            reject_checks = [r for r in results if r.failed and r.severity == Severity.REJECT]
            reasoning = (
                f"Automatic REJECT due to {len(reject_checks)} critical failure(s): "
                + "; ".join(f"{r.check_id} ({r.name})" for r in reject_checks)
            )

    return final, reasoning


def _hard_rule_pass(results: list[CheckResult]) -> Recommendation:
    """Determine recommendation based strictly on severity levels."""
    has_reject = any(r.failed and r.severity == Severity.REJECT for r in results)
    has_correction = any(r.failed and r.severity == Severity.CORRECTION for r in results)

    if has_reject:
        return Recommendation.REJECT
    if has_correction:
        return Recommendation.CORRECTION_LETTER
    return Recommendation.ACCEPT


def _claude_weighting_pass(
    results: list[CheckResult],
    hard_rec: Recommendation,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
) -> tuple[Recommendation, str]:
    """Use Claude to weigh borderline cases.

    Can escalate from ACCEPT to CORRECTION_LETTER or from
    CORRECTION_LETTER to REJECT, but never downgrade.
    """
    failed = [r for r in results if r.failed]
    if not failed:
        return Recommendation.ACCEPT, "All checks passed."

    findings = json.dumps([
        {
            "id": r.check_id,
            "name": r.name,
            "rule": r.rule,
            "severity": r.severity.value,
            "message": r.message,
            "details": r.details,
        }
        for r in failed
    ], indent=2)

    prompt = f"""You are a clerk at the North Dakota Supreme Court reviewing an appellate brief
compliance report. Based on the following findings, provide your assessment.

Current hard-rule recommendation: {hard_rec.value}

Failed checks:
{findings}

Consider:
1. Are any CORRECTION-level issues severe enough to warrant REJECT?
2. Are any NOTE-level issues collectively concerning enough to warrant a CORRECTION_LETTER?
3. Would a reasonable clerk accept, return for corrections, or reject this brief?

You may ESCALATE the recommendation (e.g., CORRECTION_LETTER → REJECT) but NEVER downgrade it
(e.g., you cannot change CORRECTION_LETTER → ACCEPT).

Return a JSON object with:
- "recommendation": one of "accept", "correction_letter", "reject"
- "reasoning": a 2-3 sentence explanation of your assessment

Return ONLY valid JSON, no markdown."""

    try:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines)

        data = json.loads(text)
        rec_str = data.get("recommendation", hard_rec.value)
        reasoning = data.get("reasoning", "")

        try:
            claude_rec = Recommendation(rec_str)
        except ValueError:
            claude_rec = hard_rec

        # Ensure no downgrade
        if _rec_rank(claude_rec.value) < _rec_rank(hard_rec.value):
            claude_rec = hard_rec
            reasoning += " (Claude attempted to downgrade; overridden by hard rules.)"

        return claude_rec, reasoning

    except Exception as e:
        return hard_rec, f"Claude weighting unavailable: {e}"


def _rec_rank(value: str) -> int:
    """Rank recommendations for comparison."""
    return {"accept": 0, "correction_letter": 1, "reject": 2}.get(value, 0)
