"""Tests for the amicus-on-rehearing brief type and the PG-004 page limit.

N.D.R.App.P. 29(b)(4), as amended effective July 1, 2026, caps an amicus brief
filed during consideration of whether to grant rehearing at 10 pages. It
previously set a 2,600-word cap.

Covers:
- Classification: an amicus cover naming the rehearing petition is an amicus
  brief under Rule 29(b), not a petition for rehearing under Rule 40
- Classification: a bare petition for rehearing is unaffected
- Classification: an ordinary amicus brief is unaffected
- PG-004 fires at the 10-page limit and cites Rule 29(b)(4)
- Oral-argument notation is not applicable on rehearing
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.brief_classifier import classify_brief
from core.checks_mechanical import _check_oral_argument, _check_page_limit
from core.constants import PAGE_LIMITS
from core.models import BriefMetadata, BriefType


def _meta(cover: str = "", brief_type: BriefType | None = None, body_pages: int = 1):
    m = BriefMetadata()
    m.cover_text = cover
    if brief_type is not None:
        m.brief_type = brief_type
    m.body_pages = body_pages
    return m


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassifyAmicusRehearing:
    @pytest.mark.parametrize("cover", [
        "BRIEF OF AMICUS CURIAE IN SUPPORT OF PETITION FOR REHEARING",
        "AMICUS CURIAE BRIEF OPPOSING THE PETITION FOR REHEARING",
        "AMICUS BRIEF OPPOSING THE REHEARING PETITION",
        "BRIEF OF AMICUS CURIAE NORTH DAKOTA ASSOCIATION OF COUNTIES "
        "IN SUPPORT OF PETITION FOR REHEARING",
    ])
    def test_amicus_on_rehearing(self, cover):
        assert classify_brief(_meta(cover)) is BriefType.AMICUS_REHEARING

    @pytest.mark.parametrize("cover", [
        "PETITION FOR REHEARING",
        "PETITION FOR REHEARING OF APPELLANT JOHN DOE",
        "REHEARING PETITION",
    ])
    def test_petition_for_rehearing_still_rule_40(self, cover):
        assert classify_brief(_meta(cover)) is BriefType.PETITION_REHEARING

    @pytest.mark.parametrize("cover", [
        "BRIEF OF AMICUS CURIAE STATE BAR ASSOCIATION OF NORTH DAKOTA",
        "BRIEF OF AMICUS CURIAE",
    ])
    def test_ordinary_amicus_unaffected(self, cover):
        assert classify_brief(_meta(cover)) is BriefType.AMICUS

    def test_letter_spaced_cover(self):
        cover = "B R I E F  O F  A M I C U S  C U R I A E  IN SUPPORT OF PETITION FOR REHEARING"
        assert classify_brief(_meta(cover)) is BriefType.AMICUS_REHEARING


# ---------------------------------------------------------------------------
# PG-004 page limit
# ---------------------------------------------------------------------------

class TestPG004PageLimit:
    def test_limit_is_ten_pages(self):
        assert PAGE_LIMITS[BriefType.AMICUS_REHEARING] == 10

    def test_over_limit_fails_with_rule_29b4(self):
        result = _check_page_limit(_meta(brief_type=BriefType.AMICUS_REHEARING, body_pages=11))
        assert result.check_id == "PG-004"
        assert result.rule == "29(b)(4)"
        assert not result.passed

    def test_at_limit_passes(self):
        result = _check_page_limit(_meta(brief_type=BriefType.AMICUS_REHEARING, body_pages=10))
        assert result.check_id == "PG-004"
        assert result.passed

    def test_does_not_borrow_the_rule_29a5_amicus_limit(self):
        """An 11-page amicus brief is fine on the merits but not on rehearing."""
        merits = _check_page_limit(_meta(brief_type=BriefType.AMICUS, body_pages=11))
        rehearing = _check_page_limit(_meta(brief_type=BriefType.AMICUS_REHEARING, body_pages=11))
        assert merits.passed
        assert not rehearing.passed

    def test_rehearing_petition_still_cites_rule_40b(self):
        result = _check_page_limit(_meta(brief_type=BriefType.PETITION_REHEARING, body_pages=11))
        assert result.check_id == "PG-005"
        assert result.rule == "40(b)"
        assert not result.passed


# ---------------------------------------------------------------------------
# Oral argument notation
# ---------------------------------------------------------------------------

class TestOralArgumentOnRehearing:
    def test_not_applicable_for_amicus_on_rehearing(self):
        result = _check_oral_argument(
            _meta("BRIEF OF AMICUS CURIAE IN SUPPORT OF PETITION FOR REHEARING",
                  brief_type=BriefType.AMICUS_REHEARING)
        )
        assert not result.applicable
