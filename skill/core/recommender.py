"""Recommendation engine: hard rules only.

Determines the final recommendation (ACCEPT, CORRECTION_LETTER, REJECT) from
check severities alone, so the same findings always produce the same
recommendation. No model is consulted; the semantic judgment that feeds it
happens earlier, when the checks themselves are evaluated.
"""

from __future__ import annotations

from core.models import CheckResult, Recommendation, Severity


def compute_recommendation(
    results: list[CheckResult],
    reasoning: str | None = None,
) -> tuple[Recommendation, str]:
    """Compute the final recommendation from check results.

    ``reasoning``, when given, replaces the generated summary; the
    undetermined-check caveat is appended either way.

    Returns (recommendation, reasoning_text).
    """
    failed = [r for r in results if r.failed]
    reject_checks = [r for r in failed if r.severity == Severity.REJECT]
    correction_checks = [r for r in failed if r.severity == Severity.CORRECTION]

    if reject_checks:
        recommendation = Recommendation.REJECT
        summary = (
            f"REJECT due to {len(reject_checks)} critical failure(s): "
            + "; ".join(f"{r.check_id} ({r.name})" for r in reject_checks)
        )
    elif correction_checks:
        recommendation = Recommendation.CORRECTION_LETTER
        summary = (
            f"Correction letter recommended due to {len(correction_checks)} issue(s): "
            + "; ".join(f"{r.check_id} ({r.name})" for r in correction_checks)
        )
    else:
        recommendation = Recommendation.ACCEPT
        summary = "All checks passed."

    return recommendation, _append_undetermined_caveat(results, reasoning or summary)


def _append_undetermined_caveat(results: list[CheckResult], reasoning: str) -> str:
    """Disclose checks that were never determined.

    The recommendation is computed from findings, and a check that could not
    be evaluated produces no finding — so it silently reads as though nothing
    were wrong with it.  Naming those checks keeps "not checked" from passing
    for "checked and clean," which matters most when a whole pass is missing
    and the recommendation would otherwise be an unqualified ACCEPT.
    """
    undetermined = [r for r in results if not r.applicable and not r.passed]
    if not undetermined:
        return reasoning

    ids = ", ".join(sorted(r.check_id for r in undetermined))
    caveat = (
        f"{len(undetermined)} check(s) could not be determined and did not "
        f"factor into this recommendation: {ids}. Those requirements are "
        f"unverified, not satisfied."
    )
    return f"{reasoning} {caveat}".strip() if reasoning else caveat
