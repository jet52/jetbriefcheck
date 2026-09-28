"""Tests for REC-001 record-citation detection under Rule 30 as amended
effective September 1, 2026.

Rule 30(b)(1) now cites a second district court record on subsequent
reference as (CV-0012 R19:2) — case type designator plus last four digits —
and 30(b)(2) requires recordings to be cited with HH:MM:SS time codes, e.g.
(Jury Trial Recording R123 01:23:45). The detector previously matched only a
bare "(R" opening, so every one of these forms went uncounted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.checks_mechanical import _check_record_citations
from core.models import BriefMetadata, BriefType


def _meta(text: str) -> BriefMetadata:
    m = BriefMetadata()
    m.brief_type = BriefType.APPELLANT
    m.full_text = text
    return m


@pytest.mark.parametrize("cite", [
    "(R156:12)",
    "(R156:12:¶3)",
    "(54-2020-CV-00012 R19:2)",
    "(CV-0012 R19:2)",
    "(Jury Trial Recording R123 01:23:45)",
])
def test_record_citation_forms_are_counted(cite):
    result = _check_record_citations(_meta(f"The court found otherwise. {cite}"))
    assert result.passed, cite


def test_no_record_citation_still_fails():
    result = _check_record_citations(_meta("See App. 15; Doc. 23; Tr. 45."))
    assert not result.passed
