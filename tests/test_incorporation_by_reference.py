"""Tests for CNT-005, N.D.R.App.P. 28(f)(2) as added effective September 1, 2026:
"A party may not incorporate by reference the contents of a brief filed
elsewhere or in another case."

The rule speaks to parties, so the check is gated to party briefs: an amicus
brief reports not applicable, and an unclassified brief reports not
determined rather than silently passing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.models import BriefType, Severity
from core.semantic_definitions import SEMANTIC_CHECKS, gated_check_result

CNT_005 = next(c for c in SEMANTIC_CHECKS if c[0] == "CNT-005")
PARTY_TYPES = {
    BriefType.APPELLANT, BriefType.APPELLEE, BriefType.REPLY,
    BriefType.CROSS_APPEAL, BriefType.PETITION_REHEARING,
}


def test_definition():
    cid, name, rule, types, severity, _desc = CNT_005
    assert rule == "28(f)(2)"
    assert severity is Severity.CORRECTION
    assert set(types) == PARTY_TYPES


@pytest.mark.parametrize("bt", [BriefType.AMICUS, BriefType.AMICUS_REHEARING])
def test_amicus_is_not_applicable(bt):
    cid, name, rule, _types, severity, _desc = CNT_005
    r = gated_check_result(cid, name, rule, severity, bt)
    assert r.passed is True and r.applicable is False


def test_unknown_type_is_not_determined():
    cid, name, rule, _types, severity, _desc = CNT_005
    r = gated_check_result(cid, name, rule, severity, BriefType.UNKNOWN)
    assert r.passed is False and r.applicable is False
    assert "not determined" in r.message.lower()


@pytest.mark.parametrize("doc", ["SKILL.md", "references/check-definitions.md"])
def test_documented(doc):
    text = (PROJECT_DIR / "skill" / doc).read_text(encoding="utf-8")
    assert "CNT-005 — No Incorporation by Reference" in text
    assert "28(f)(2)" in text
