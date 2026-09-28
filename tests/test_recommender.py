"""The hard-rule recommendation, and the "unevaluated means undetermined" rule.

The recommendation is computed from check severities alone. A check that was
never evaluated produces no finding, so it would silently read as clean; the
reasoning therefore names every undetermined check. Checks that genuinely do
not apply to the brief type are a different thing and are not named.

Also covers PRV-001 (minor names redacted — N.D.R.Ct. 3.4(b)(1)(C), and
N.D.R.App.P. 14(a)(5) to the same effect), which was once specified in the
references but never registered, so it never ran.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.models import BriefType, CheckResult, Recommendation, Severity
from core.recommender import compute_recommendation
from core.semantic_definitions import SEMANTIC_CHECKS, gated_check_result

_spec = importlib.util.spec_from_file_location(
    "build_report", PROJECT_DIR / "skill" / "scripts" / "build_report.py")
build_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_report)


def _result(cid, passed=True, severity=Severity.CORRECTION, applicable=True):
    return CheckResult(check_id=cid, name=cid, rule="x", passed=passed,
                       severity=severity, message="m", applicable=applicable)


def _all_passed(brief_type=BriefType.APPELLANT):
    """Every semantic check, evaluated and passed or genuinely inapplicable."""
    out = []
    for cid, name, rule, types, severity, _ in SEMANTIC_CHECKS:
        if types is None or brief_type in types:
            out.append(_result(cid, severity=severity))
        else:
            out.append(gated_check_result(cid, name, rule, severity, brief_type))
    return out


class TestPrv001Registration:

    def test_registered_for_every_brief_type(self):
        """PRV-001 is case-type triggered, so no brief type filters it out."""
        entry = next(c for c in SEMANTIC_CHECKS if c[0] == "PRV-001")
        assert entry[3] is None
        assert entry[4] is Severity.CORRECTION

    def test_cites_the_privacy_rule(self):
        entry = next(c for c in SEMANTIC_CHECKS if c[0] == "PRV-001")
        assert "3.4" in entry[2]


class TestHardRules:

    def test_reject_wins(self):
        rec, reasoning = compute_recommendation([
            _result("A", passed=False, severity=Severity.REJECT),
            _result("B", passed=False, severity=Severity.CORRECTION),
        ])
        assert rec == Recommendation.REJECT
        assert reasoning.startswith("REJECT due to 1 critical failure(s): A")

    def test_correction_without_reject(self):
        rec, _ = compute_recommendation([
            _result("B", passed=False, severity=Severity.CORRECTION),
            _result("C", passed=False, severity=Severity.NOTE),
        ])
        assert rec == Recommendation.CORRECTION_LETTER

    def test_notes_alone_accept(self):
        rec, _ = compute_recommendation([_result("C", passed=False, severity=Severity.NOTE)])
        assert rec == Recommendation.ACCEPT

    def test_prv001_violation_drives_a_correction_letter(self):
        results = [r for r in _all_passed() if r.check_id != "PRV-001"]
        results.append(_result("PRV-001", passed=False))
        rec, _ = compute_recommendation(results)
        assert rec == Recommendation.CORRECTION_LETTER


class TestUndeterminedCaveat:

    def test_omitted_semantic_check_is_disclosed(self):
        """A semantic result left out of the JSON must not read as clean."""
        reported = [r for r in _all_passed() if r.check_id != "PRV-001"]
        results = reported + build_report._missing_semantic_results(
            reported, BriefType.APPELLANT)
        rec, reasoning = compute_recommendation(results)
        assert rec == Recommendation.ACCEPT
        assert "could not be determined" in reasoning
        assert "unverified, not satisfied" in reasoning
        assert "PRV-001" in reasoning

    def test_no_caveat_when_everything_was_determined(self):
        _, reasoning = compute_recommendation(_all_passed())
        assert "could not be determined" not in reasoning

    def test_inapplicable_is_not_reported_as_undetermined(self):
        results = _all_passed(BriefType.APPELLANT)
        amicus = [r for r in results if r.check_id in ("SEC-014", "SEC-015")]
        assert amicus and all(not r.applicable and r.passed for r in amicus)
        _, reasoning = compute_recommendation(results)
        assert "SEC-014" not in reasoning

    def test_unknown_brief_type_is_disclosed(self):
        _, reasoning = compute_recommendation(_all_passed(BriefType.UNKNOWN))
        assert "SEC-006" in reasoning

    def test_caller_reasoning_keeps_the_caveat(self):
        reported = [r for r in _all_passed() if r.check_id != "PRV-001"]
        results = reported + build_report._missing_semantic_results(
            reported, BriefType.APPELLANT)
        _, reasoning = compute_recommendation(results, "Clerk summary.")
        assert reasoning.startswith("Clerk summary.")
        assert "PRV-001" in reasoning
