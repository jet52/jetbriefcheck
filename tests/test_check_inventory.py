"""Guard against drift between the check implementations and the docs.

Three places describe the check inventory and must agree:

* ``skill/core/`` — the implementations, the only source that actually runs;
* ``skill/references/check-definitions.md`` — the reference the semantic
  evaluation is written against;
* ``skill/SKILL.md`` — self-contained, and the only copy that ships when the
  skill is installed from the zip.

Drift here is not cosmetic.  PRV-001 (minor names redacted, N.D.R.Ct.
3.4(b)(1)(C) and Rule 14(a)(5)) was fully specified in both documents,
listed as applying to every brief type, and referenced by name in the
evaluation prompt — but was never added to ``SEMANTIC_CHECKS``, so it never
ran.  A brief exposing a minor's name would have passed silently.  These
tests would have caught it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.checks_semantic import SEMANTIC_CHECKS

SKILL_DIR = PROJECT_DIR / "skill"
CHECK_ID_RE = re.compile(r"\b([A-Z]{2,4}-\d{3})\b")
QUOTED_ID_RE = re.compile(r"[\"']([A-Z]{2,4}-\d{3})[\"']")


def _ids_in_markdown(path: Path) -> set[str]:
    return set(CHECK_ID_RE.findall(path.read_text()))


def _ids_in_core() -> set[str]:
    found: set[str] = set()
    for py in (SKILL_DIR / "core").glob("*.py"):
        found |= set(QUOTED_ID_RE.findall(py.read_text()))
    return found


@pytest.fixture(scope="module")
def core_ids() -> set[str]:
    return _ids_in_core()


@pytest.fixture(scope="module")
def definition_ids() -> set[str]:
    return _ids_in_markdown(SKILL_DIR / "references" / "check-definitions.md")


@pytest.fixture(scope="module")
def skill_md_ids() -> set[str]:
    return _ids_in_markdown(SKILL_DIR / "SKILL.md")


class TestCheckInventory:

    def test_every_implemented_check_is_documented(self, core_ids, definition_ids):
        missing = sorted(core_ids - definition_ids)
        assert not missing, (
            f"implemented but absent from check-definitions.md: {missing}"
        )

    def test_every_documented_check_is_implemented(self, core_ids, definition_ids):
        """The PRV-001 failure mode: documented, described, never run."""
        missing = sorted(definition_ids - core_ids)
        assert not missing, (
            f"documented in check-definitions.md but not implemented: {missing}"
        )

    def test_skill_md_matches_implementations(self, core_ids, skill_md_ids):
        """SKILL.md is the only copy that ships in the zip — it must be complete."""
        assert sorted(skill_md_ids) == sorted(core_ids), (
            f"only in SKILL.md: {sorted(skill_md_ids - core_ids)}; "
            f"only in core: {sorted(core_ids - skill_md_ids)}"
        )

    def test_semantic_check_ids_are_unique(self):
        ids = [c[0] for c in SEMANTIC_CHECKS]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        assert not duplicates, f"duplicate semantic check ids: {duplicates}"

    def test_prv_001_is_registered(self):
        """Explicit guard on the check that was missing.

        Minor identity protection is the highest-consequence privacy check in
        the set; a silent omission here exposes a child's name.
        """
        ids = [c[0] for c in SEMANTIC_CHECKS]
        assert "PRV-001" in ids

    def test_privacy_checks_apply_to_all_brief_types(self):
        """PRV checks are case-type triggered, not brief-type limited."""
        for check in SEMANTIC_CHECKS:
            check_id, _, _, applicable_types = check[0], check[1], check[2], check[3]
            if check_id.startswith("PRV-"):
                assert applicable_types is None, (
                    f"{check_id} should apply to all brief types"
                )
