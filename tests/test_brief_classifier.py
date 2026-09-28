"""Brief-type classification from cover text.

Getting this wrong is expensive and quiet.  ``BriefType.UNKNOWN`` is not in
``PAGE_LIMITS`` and filters out 16 type-gated semantic checks, so a
misclassified brief yields a report that is silently missing its Statement
of Issues, Statement of Facts, Argument and Conclusion checks — with nothing
in the output saying so.

Measured against the 22 briefs in test-data/, the classifier was right on 12.
Two defects accounted for all ten failures:

1. ``_normalize`` collapses every run of whitespace to a single space, but
   the "brief of X" window required a comma, newline or double space to close
   it.  On the commonest cover format — "BRIEF OF APPELLANT" followed by the
   appeal caption — nothing closed the window, the match failed, and the
   fallback declined to guess.  Plain ``BRIEF OF APPELLANT`` returned UNKNOWN.

2. Compound designations resolved left to right, checking appellee-side words
   first as "more specific".  But a cover names the trial-court role first and
   the appellate role last, so "RESPONDENT - APPELLANT" resolved to appellee.

The covers below are fabricated, but each reproduces a shape that appears in
test-data/.  The real briefs are not committed, so the end-to-end check
against them lives in ``TestAgainstRealBriefs`` and skips when absent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.brief_classifier import _designation_role, classify_brief
from core.models import BriefMetadata, BriefType

CAPTION = """IN THE SUPREME COURT OF THE STATE OF NORTH DAKOTA

Supreme Court No. 20990003

Avery Lindquist,
                              Plaintiff-Appellant,
vs.
Dana Whitford,
                              Defendant-Appellee.
"""

TRAILER = """
APPEAL FROM THE AMENDED JUDGMENT ENTERED
MARCH 4, 2026, IN THE DISTRICT COURT,
CASS COUNTY, EAST CENTRAL JUDICIAL DISTRICT

ORAL ARGUMENT REQUESTED
"""


def _cover(title: str) -> BriefMetadata:
    """A full cover with *title* as the brief's own title line."""
    return BriefMetadata(cover_text=f"{CAPTION}\n{title}\n{TRAILER}")


class TestBriefTitleForms:
    """Title lines observed on real covers, reproduced with invented names."""

    @pytest.mark.parametrize("title,expected", [
        # The plain forms that used to return UNKNOWN
        ("BRIEF OF APPELLANT", BriefType.APPELLANT),
        ("BRIEF OF APPELLEE", BriefType.APPELLEE),
        ("BRIEF OF THE APPELLANT", BriefType.APPELLANT),
        # Compound designations — the appellate role trails
        ("BRIEF OF PLAINTIFF-APPELLANT", BriefType.APPELLANT),
        ("BRIEF OF DEFENDANT-APPELLEE", BriefType.APPELLEE),
        ("BRIEF OF RESPONDENT – APPELLANT", BriefType.APPELLANT),
        ("BRIEF OF RESPONDENT/APPELLANT D. B.", BriefType.APPELLANT),
        ("BRIEF OF PETITIONER-APPELLEE", BriefType.APPELLEE),
        ("BRIEF OF DEFENDANT/APPELLANT", BriefType.APPELLANT),
        # "X brief" direction
        ("APPELLANT'S BRIEF", BriefType.APPELLANT),
        ("APPELLEE'S BRIEF", BriefType.APPELLEE),
        # Other types keep their precedence over the party designation
        ("REPLY BRIEF OF PLAINTIFF-APPELLANT", BriefType.REPLY),
        ("BRIEF OF AMICUS CURIAE", BriefType.AMICUS),
        ("BRIEF OF CROSS-APPELLANT", BriefType.CROSS_APPEAL),
    ])
    def test_title(self, title, expected):
        assert classify_brief(_cover(title)) == expected

    def test_petition_for_rehearing_outranks_party_designation(self):
        cover = _cover("PETITION FOR REHEARING BY PLAINTIFF-APPELLANT")
        assert classify_brief(cover) == BriefType.PETITION_REHEARING

    def test_amicus_on_rehearing_is_governed_by_rule_29(self):
        cover = _cover("BRIEF OF AMICUS CURIAE IN SUPPORT OF PETITION FOR REHEARING")
        assert classify_brief(cover) == BriefType.AMICUS_REHEARING


class TestDesignationRole:
    """The trailing-role rule, in isolation."""

    @pytest.mark.parametrize("window,expected", [
        ("appellant", BriefType.APPELLANT),
        ("appellee", BriefType.APPELLEE),
        ("plaintiff-appellant", BriefType.APPELLANT),
        ("defendant-appellee", BriefType.APPELLEE),
        ("respondent - appellant", BriefType.APPELLANT),
        ("respondent/appellant", BriefType.APPELLANT),
        ("petitioner-appellee", BriefType.APPELLEE),
        ("intervenor-appellant", BriefType.APPELLANT),
    ])
    def test_trailing_role_governs(self, window, expected):
        assert _designation_role(window) == expected

    def test_designation_stops_at_prose(self):
        """A later mention outside the designation must not steal the call."""
        assert _designation_role(
            "appellant in response to the brief of appellee"
        ) == BriefType.APPELLANT

    def test_trial_court_role_alone_decides_nothing(self):
        """"Plaintiff" says who sued, not who is appealing."""
        assert _designation_role("plaintiff jordan marlowe") is None

    def test_no_role_words(self):
        assert _designation_role("the honorable dana whitford presiding") is None

    def test_respondent_alone_is_appellee_side(self):
        assert _designation_role("respondent") == BriefType.APPELLEE


class TestNormalizationSurvives:
    """Fuzz tolerance must not regress with the new window."""

    @pytest.mark.parametrize("title", [
        "BRIEF OF PLAINTIFF–APPELLANT",     # en dash
        "BRIEF OF PLAINTIFF—APPELLANT",     # em dash
        "BRIEF OF PLAINTIFF-APPELLANT​",    # zero-width space
        "BRIEF OF PLAINTIFF-APPELLANTS",         # plural
        "Brief of Plaintiff-Appellant",          # mixed case
    ])
    def test_variant_still_classifies(self, title):
        assert classify_brief(_cover(title)) == BriefType.APPELLANT

    def test_caption_alone_does_not_decide(self):
        """Without a brief title, the classifier must decline rather than guess.

        The caption names both parties; picking one is a coin flip, and the
        old code's fallback picked whichever appeared last.
        """
        assert classify_brief(BriefMetadata(cover_text=CAPTION)) == BriefType.UNKNOWN


@pytest.mark.skipif(
    not (PROJECT_DIR / "test-data").is_dir(),
    reason="test-data/ is not committed; run locally for the end-to-end check",
)
class TestAgainstRealBriefs:
    """End-to-end over test-data/, labelled by the filename convention.

    The convention was validated by reading the covers: Apt-Br files title
    themselves "BRIEF OF APPELLANT" (or a compound ending in appellant),
    Ape-Br files "BRIEF OF APPELLEE".
    """

    @staticmethod
    def _expected(name: str):
        if re.search(r"Reply", name, re.I):
            return BriefType.REPLY
        if re.search(r"Ape-Br", name):
            return BriefType.APPELLEE
        if re.search(r"Apt-Br|Appellant", name, re.I):
            return BriefType.APPELLANT
        if re.search(r"Appellee", name, re.I):
            return BriefType.APPELLEE
        return None

    def test_every_labelled_brief_classifies_correctly(self):
        from core.pdf_extract import extract_brief

        wrong = []
        checked = 0
        for pdf in sorted((PROJECT_DIR / "test-data").glob("*.pdf")):
            if pdf.name.startswith("compliance-"):
                continue
            expected = self._expected(pdf.name)
            if expected is None:
                continue
            checked += 1
            got = classify_brief(extract_brief(str(pdf)))
            if got != expected:
                wrong.append(f"{pdf.name}: expected {expected.value}, got {got.value}")

        assert checked >= 20, f"expected the full sample, saw {checked}"
        assert not wrong, "misclassified:\n  " + "\n  ".join(wrong)
