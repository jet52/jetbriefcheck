"""PRV-001 wiring, and the "unevaluated means undetermined" rule.

PRV-001 (minor names redacted — N.D.R.Ct. 3.4(b)(1)(C), and N.D.R.App.P.
14(a)(5) to the same effect) was specified in the reference and named in the
evaluation prompt but never registered, so it never ran.  Registering it is
only half the job: a check that reports "passed" when it was never evaluated
is worse than one that is missing, because the report then asserts
compliance.  These tests cover both halves.

No API call is made.  The client is mocked, so the prompt that would be sent
is inspected locally and no brief text leaves the machine.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.checks_semantic import (
    SEMANTIC_CHECKS,
    _fallback_results,
    _parse_semantic_response,
    run_semantic_checks,
)
from core.models import BriefMetadata, BriefType, Recommendation, Severity
from core.recommender import compute_recommendation


# A wholly fabricated brief.  The minor is referred to by initials in most
# places and by first name once — the failure mode the check exists to catch.
SYNTHETIC_BRIEF = """
IN THE SUPREME COURT OF THE STATE OF NORTH DAKOTA

Jordan Marlowe, Plaintiff-Appellant, v. Riley Marlowe, Defendant-Appellee.

STATEMENT OF FACTS

[1] The parties are the parents of one minor child, T.M., born in 2016.
The district court awarded primary residential responsibility to the
appellee. T.M. has resided with the appellee since the separation.

[2] The custody investigator testified that Tobias had adjusted well to the
new school, and that T.M.'s teachers reported no concerns.

ARGUMENT

[3] The district court's findings as to T.M.'s best interests were clearly
erroneous.
"""


def _metadata(text: str = SYNTHETIC_BRIEF,
              brief_type: BriefType = BriefType.APPELLANT) -> BriefMetadata:
    return BriefMetadata(
        pages=[],
        total_pages=12,
        full_text=text,
        brief_type=brief_type,
        word_count=len(text.split()),
    )


def _mock_client(payload: str):
    """Build a mocked anthropic client returning *payload* as the response."""
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=payload)]
    client.messages.create.return_value = message
    return client


# ===================================================================
# PRV-001 registration and prompt wiring
# ===================================================================

class TestPrv001Wiring:

    def test_registered_for_every_brief_type(self):
        """PRV-001 is case-type triggered, so no brief type filters it out."""
        entry = next(c for c in SEMANTIC_CHECKS if c[0] == "PRV-001")
        assert entry[3] is None, "applicable_types must be None (all types)"
        assert entry[4] == Severity.CORRECTION

    def test_cites_the_privacy_rule(self):
        entry = next(c for c in SEMANTIC_CHECKS if c[0] == "PRV-001")
        assert "3.4" in entry[2]

    @pytest.mark.parametrize("brief_type", [
        BriefType.APPELLANT, BriefType.APPELLEE, BriefType.REPLY,
        BriefType.AMICUS, BriefType.PETITION_REHEARING,
    ])
    def test_reaches_the_model_for_every_brief_type(self, brief_type):
        """The check must be in the payload actually sent, not just the list."""
        client = _mock_client("[]")
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            run_semantic_checks(_metadata(brief_type=brief_type), api_key="test")

        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert '"id": "PRV-001"' in prompt, f"PRV-001 not sent for {brief_type}"

    def test_prompt_carries_the_guidance(self):
        """Guidance must travel with the check, not just its name."""
        client = _mock_client("[]")
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            run_semantic_checks(_metadata(), api_key="test")

        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "- PRV-001:" in prompt
        assert "initials" in prompt
        # The exemption that does NOT apply in an ordinary custody appeal
        assert "3.4(b)(3)(E)" in prompt
        # The characteristic failure mode
        assert "quoted testimony" in prompt

    def test_failure_verdict_parses_into_a_finding(self):
        """A PRV-001 violation comes back as a real, actionable finding."""
        payload = json.dumps([{
            "id": "PRV-001",
            "passed": False,
            "message": "Minor's first name 'Tobias' appears at paragraph 2 "
                       "while initials T.M. are used elsewhere.",
        }])
        client = _mock_client(payload)
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(), api_key="test")

        prv = next(r for r in results if r.check_id == "PRV-001")
        assert prv.passed is False
        assert prv.applicable is True
        assert prv.failed is True, "must count as a finding"
        assert prv.severity == Severity.CORRECTION
        assert "Tobias" in prv.message

    def test_violation_drives_a_correction_letter(self):
        """End to end: a minor's name in the brief must not yield ACCEPT."""
        payload = json.dumps([{
            "id": "PRV-001", "passed": False,
            "message": "Minor's given name appears in the statement of facts.",
        }])
        client = _mock_client(payload)
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(), api_key="test")

        rec, _ = compute_recommendation(results, use_claude_weighting=False)
        assert rec != Recommendation.ACCEPT


# ===================================================================
# Unevaluated checks must not read as compliant
# ===================================================================

class TestUnevaluatedChecksAreUndetermined:

    def test_check_absent_from_response_is_undetermined(self):
        """The model answered, but said nothing about PRV-001."""
        payload = json.dumps([{"id": "SEC-001", "passed": True, "message": "TOC present."}])
        client = _mock_client(payload)
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(), api_key="test")

        prv = next(r for r in results if r.check_id == "PRV-001")
        assert prv.applicable is False, "unevaluated must not count as evaluated"
        assert prv.passed is False, "unevaluated must not count as compliant"
        assert prv.failed is False, "unevaluated must not count as a finding"

    def test_unparseable_response_marks_everything_undetermined(self):
        """The whole-pass failure: nothing was checked, so nothing passed."""
        results = _fallback_results(
            [("PRV-001", "Privacy: Minor Names Redacted", "N.D.R.Ct. 3.4(b)(1)(C)",
              Severity.CORRECTION, "desc")],
            "Claude API returned non-JSON response.",
        )
        assert all(not r.applicable for r in results)
        assert all(not r.passed for r in results)
        assert all(not r.failed for r in results)

    def test_garbage_response_does_not_populate_passed_checks(self):
        """A report's "Passed Checks" list must never be fiction."""
        client = _mock_client("I'm sorry, I can't help with that.")
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(), api_key="test")

        evaluated = [r for r in results if r.applicable and r.passed]
        assert evaluated == [], "no check may report as passed when none ran"

    def test_recommendation_discloses_undetermined_checks(self):
        """ACCEPT on an un-run analysis must at least say so."""
        client = _mock_client("not json at all")
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(), api_key="test")

        rec, reasoning = compute_recommendation(results, use_claude_weighting=False)
        assert "could not be determined" in reasoning
        assert "unverified, not satisfied" in reasoning
        assert "PRV-001" in reasoning

    def test_no_caveat_when_everything_was_determined(self):
        payload = json.dumps([
            {"id": cid, "passed": True, "message": "ok"}
            for cid, *_ in SEMANTIC_CHECKS
        ])
        client = _mock_client(payload)
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(), api_key="test")

        _, reasoning = compute_recommendation(results, use_claude_weighting=False)
        assert "could not be determined" not in reasoning

    def test_brief_type_inapplicable_is_not_reported_as_undetermined(self):
        """A check that genuinely does not apply is a different thing."""
        payload = json.dumps([{"id": "PRV-001", "passed": True, "message": "No minors."}])
        client = _mock_client(payload)
        with patch("core.checks_semantic.anthropic.Anthropic", return_value=client):
            results = run_semantic_checks(_metadata(brief_type=BriefType.APPELLANT),
                                          api_key="test")

        # Amicus-only checks are inapplicable here, and are marked passed=True
        # so they are not swept into the undetermined caveat.
        amicus = [r for r in results if r.check_id in ("SEC-014", "SEC-015")]
        assert amicus, "expected amicus checks in the result set"
        assert all(not r.applicable and r.passed for r in amicus)

        _, reasoning = compute_recommendation(results, use_claude_weighting=False)
        assert "SEC-014" not in reasoning


# ===================================================================
# Optional live validation
# ===================================================================

LIVE = os.environ.get("JETBRIEFCHECK_LIVE_API") == "1"


@pytest.mark.skipif(
    not LIVE or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live API test; set JETBRIEFCHECK_LIVE_API=1 and ANTHROPIC_API_KEY to run",
)
class TestPrv001Live:
    """End-to-end check against the real API. Opt-in — it costs a call.

        JETBRIEFCHECK_LIVE_API=1 pytest tests/test_semantic_prv001.py -k Live

    The brief text is wholly fabricated (see SYNTHETIC_BRIEF): no real case
    content is sent anywhere. The mocked tests above prove the wiring; this
    proves the model actually catches the violation the check exists for.
    """

    def test_catches_the_minor_name_slip(self):
        results = run_semantic_checks(_metadata())
        prv = next(r for r in results if r.check_id == "PRV-001")
        assert prv.applicable is True, (
            f"PRV-001 was not evaluated: {prv.message}"
        )
        assert prv.passed is False, (
            "PRV-001 missed a minor's given name used alongside initials; "
            f"model said: {prv.message}"
        )

    def test_clean_brief_passes(self):
        """Guard the other direction — initials throughout must not flag."""
        clean = SYNTHETIC_BRIEF.replace("Tobias", "T.M.")
        results = run_semantic_checks(_metadata(clean))
        prv = next(r for r in results if r.check_id == "PRV-001")
        assert prv.applicable is True
        assert prv.passed is True, (
            f"false positive on a compliant brief: {prv.message}"
        )
