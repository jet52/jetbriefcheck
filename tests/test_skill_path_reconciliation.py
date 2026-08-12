"""The skill execution path: semantic results written by Claude, not the API.

Two execution paths exist and they are easy to conflate:

* **Skill path** (SKILL.md) — "You (Claude) perform the semantic analysis
  directly — no API call needed."  The assistant writes
  ``<stem>-semantic.json`` and ``build_report.py`` merges it.  This is how
  the skill runs under a Claude subscription, and it never imports
  ``anthropic`` — which is not in ``skill/requirements.txt``.
* **API path** (``core.checks_semantic``) — used by the Flask app and the
  CLI with a key.

SKILL.md requires every semantic check to appear in the JSON, but nothing
enforced it.  A check omitted from the JSON vanished from the report
entirely: no row, no tally, no trace it was meant to run.  These tests cover
the reconciliation that closes that gap.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.models import BriefType, CheckResult, Severity
from core.semantic_definitions import SEMANTIC_CHECKS


def _load_build_report():
    """Import build_report.py by path (it lives in scripts/, not a package)."""
    path = PROJECT_DIR / "skill" / "scripts" / "build_report.py"
    spec = importlib.util.spec_from_file_location("build_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_report = _load_build_report()


def _result(check_id: str, passed: bool = True) -> CheckResult:
    return CheckResult(
        check_id=check_id, name="x", rule="28(b)(1)",
        passed=passed, severity=Severity.CORRECTION, message="reported",
    )


ALL_TYPE_IDS = [c[0] for c in SEMANTIC_CHECKS if c[3] is None]


class TestSkillPathHasNoAnthropicDependency:
    """The deployed skill installs only PyMuPDF; anthropic must not be needed."""

    # Run in a subprocess with `anthropic` forced to be unimportable, which
    # is the deployed skill's actual condition — string-matching the source
    # would only catch the spelling, not the dependency.
    # MetaPathFinder.find_spec — find_module was removed in Python 3.12.
    BLOCK_ANTHROPIC = (
        "import sys\n"
        "class _Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'anthropic' or name.startswith('anthropic.'):\n"
        "            raise ImportError('anthropic is not installed')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Blocker())\n"
        "sys.modules.pop('anthropic', None)\n"
        "sys.path.insert(0, {skill!r})\n"
    )

    def _run_without_anthropic(self, body: str):
        import subprocess
        script = self.BLOCK_ANTHROPIC.format(skill=str(PROJECT_DIR / "skill")) + body
        return subprocess.run([sys.executable, "-c", script],
                              capture_output=True, text=True)

    def test_anthropic_really_is_blocked(self):
        """Guard the guard — otherwise the two tests below prove nothing."""
        r = self._run_without_anthropic("import anthropic")
        assert r.returncode != 0
        assert "anthropic is not installed" in r.stderr

    def test_semantic_definitions_imports_without_anthropic(self):
        r = self._run_without_anthropic(
            "from core.semantic_definitions import SEMANTIC_CHECKS\n"
            "print(len(SEMANTIC_CHECKS))\n"
        )
        assert r.returncode == 0, r.stderr
        assert int(r.stdout.strip()) == len(SEMANTIC_CHECKS)

    def test_build_report_imports_without_anthropic(self):
        """The deployed skill's venv has only PyMuPDF; this must still load."""
        path = PROJECT_DIR / "skill" / "scripts" / "build_report.py"
        r = self._run_without_anthropic(
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('br', {str(path)!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "print('ok')\n"
        )
        assert r.returncode == 0, r.stderr
        assert "ok" in r.stdout

    def test_definitions_are_shared_with_the_api_path(self):
        """One inventory, so the two paths cannot disagree about what exists."""
        from core.checks_semantic import SEMANTIC_CHECKS as api_side
        assert api_side is SEMANTIC_CHECKS


class TestMissingSemanticResults:

    def test_omitted_check_becomes_undetermined(self):
        """The gap: a check absent from the JSON used to vanish silently."""
        reported = [_result(cid) for cid in ALL_TYPE_IDS if cid != "PRV-001"]
        filled = build_report._missing_semantic_results(reported, BriefType.APPELLANT)

        prv = next(r for r in filled if r.check_id == "PRV-001")
        assert prv.applicable is False
        assert prv.passed is False
        assert prv.failed is False
        assert "not determined" in prv.message.lower()

    def test_nothing_added_when_all_reported(self):
        reported = [_result(c[0]) for c in SEMANTIC_CHECKS]
        assert build_report._missing_semantic_results(reported, BriefType.APPELLANT) == []

    def test_every_check_ends_up_in_the_report(self):
        """Whatever the assistant writes, the report accounts for all of them."""
        reported = [_result("SEC-001")]
        filled = build_report._missing_semantic_results(reported, BriefType.APPELLANT)
        covered = {r.check_id for r in reported} | {r.check_id for r in filled}
        assert covered == {c[0] for c in SEMANTIC_CHECKS}

    def test_brief_type_inapplicable_is_labelled_as_such(self):
        """An amicus-only check absent from an appellant report is expected."""
        filled = build_report._missing_semantic_results([], BriefType.APPELLANT)
        sec014 = next(r for r in filled if r.check_id == "SEC-014")
        assert sec014.applicable is False
        assert sec014.passed is True, "expected absence, not an unverified gap"
        assert "not applicable" in sec014.message.lower()

    def test_amicus_check_missing_from_an_amicus_brief_is_undetermined(self):
        """The same check on the type it applies to is a real gap."""
        filled = build_report._missing_semantic_results([], BriefType.AMICUS)
        sec014 = next(r for r in filled if r.check_id == "SEC-014")
        assert sec014.passed is False
        assert "not determined" in sec014.message.lower()

    def test_undetermined_checks_do_not_change_the_recommendation(self):
        """An empty semantic JSON must not manufacture failures either."""
        filled = build_report._missing_semantic_results([], BriefType.APPELLANT)
        rec, _ = build_report._hard_rule_recommendation(filled)
        assert rec.value == "accept", (
            "undetermined checks must not count as findings"
        )

    def test_reported_failure_still_drives_the_recommendation(self):
        reported = [_result("PRV-001", passed=False)]
        filled = build_report._missing_semantic_results(reported, BriefType.APPELLANT)
        rec, reasoning = build_report._hard_rule_recommendation(reported + filled)
        assert rec.value == "correction_letter"
        assert "PRV-001" in reasoning
