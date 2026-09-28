"""Citation grounding: text preparation, noise suppression, reporting.

Verification is ndlaw's ``check_draft``. This module covers only what
``check_draft`` cannot know — that it is reading a PDF extraction of an
appellate brief — plus the firewall that keeps its findings out of the
compliance determination.

Both suppression rules here were derived from live runs against filed
briefs, not from imagination, and each exists because the naive behaviour
put a false flag on a correctly drafted brief.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.citations import (
    FLAG_MISQUOTATION,
    FLAG_NAME_DRIFT,
    FLAG_UNRESOLVED,
    FLAG_UNRESOLVED_AUTHORITY,
    CitationFinding,
    CitationReview,
    misquotation_is_comparable,
    clean_draft_text,
    name_drift_is_real,
    normalize_caption,
    paragraph_for_context,
)
from core.models import BriefType, ComplianceReport, Recommendation
from core.report_builder import build_html_report


# Shaped like a real check_draft return, carrying the two false positives a
# filed brief actually produced.
LIVE_PAYLOAD = {
    "summary": {
        "checks_run": ["citations", "quotations"],
        "case_citations": 13, "cases_resolved": 7,
        "authority_citations": 0,
        "quotations": 2, "quotations_checked": 2, "quotations_clear": 1,
    },
    "flags": [
        {"severity": "S2", "type": "unresolved_case_cite",
         "message": "Citation '10 N.W.3d 587' does not resolve to any ND opinion.",
         "cited_as": "10 N.W.3d 587",
         "draft_context": "same as that of a motion to suppress. State v. Reiswig"},
        {"severity": "S5", "type": "case_name_drift", "message": "drift",
         "written_name": "State v. P.K.",
         "canonical_name": "State, et al. v. P.K. (Confidential)",
         "cited_as": ["2020 ND 235", "951 N.W.2d 254"]},
        {"severity": "S5", "type": "case_name_drift", "message": "drift",
         "written_name": "Lucas v. Lucas",
         "canonical_name": "Lucas v. Lucas (cross-reference w/20990001)",
         "cited_as": ["2014 ND 2"]},
    ],
    "unchecked": {},
}


class TestCleanDraftText:
    """Page numbers extraction leaves behind, mid-quotation."""

    def test_removes_a_page_number_on_its_own_line(self):
        raw = "afford a clear understanding of \n\n8 \n \nits decision."
        out = clean_draft_text(raw)
        assert "8" not in out
        assert "understanding of" in out and "its decision." in out

    def test_removes_two_page_breaks_close_together(self):
        out = clean_draft_text("text here \n12 \n \n13 \n more text")
        assert "12" not in out and "13" not in out

    def test_keeps_paragraph_markers(self):
        """Markers are how a finding is located in the brief."""
        raw = "[¶ 10] The court held.\n\n[¶ 11] The court also held."
        out = clean_draft_text(raw)
        assert "[¶ 10]" in out and "[¶ 11]" in out

    def test_keeps_numbers_inside_a_line(self):
        """A page number is alone on its line; a statutory number is not."""
        raw = "See N.D.C.C. 14-09-06.2 and the 3 factors listed there."
        assert clean_draft_text(raw) == raw

    def test_empty_input(self):
        assert clean_draft_text("") == ""


class TestNormalizeCaption:
    """ndlaw captions carry bookkeeping that is not part of the case name."""

    @pytest.mark.parametrize("raw,expected", [
        ("Lucas v. Lucas (cross-reference w/20990001)", "lucas v lucas"),
        ("State, et al. v. P.K. (Confidential)", "state v p k"),
        ("Davis, et al. v. Romanyshyn", "davis v romanyshyn"),
        ("State v. Juntunen", "state v juntunen"),
    ])
    def test_annotations_and_filler_are_stripped(self, raw, expected):
        assert normalize_caption(raw) == expected


class TestNameDriftSuppression:
    """Derived from live runs — each case was a real false positive."""

    @pytest.mark.parametrize("written,canonical", [
        # ndlaw scored these 0.5 and 0.491; both briefs cite correctly
        ("State v. P.K.", "State, et al. v. P.K. (Confidential)"),
        ("Lucas v. Lucas", "Lucas v. Lucas (cross-reference w/20990001)"),
        ("Davis o/b/o HJR & CER v. Romanyshyn", "Davis, et al. v. Romanyshyn"),
        ("Koon v. State", "Koon v. State"),
    ])
    def test_bookkeeping_and_style_are_not_drift(self, written, canonical):
        assert name_drift_is_real(written, canonical) is False

    @pytest.mark.parametrize("written,canonical", [
        ("Smith v. Jones", "Torgerson v. Bexley"),
        ("State v. Anderson", "In re Estate of Vollmer"),
    ])
    def test_a_different_case_is_drift(self, written, canonical):
        assert name_drift_is_real(written, canonical) is True

    def test_missing_name_is_not_drift(self):
        assert name_drift_is_real("", "State v. Juntunen") is False


class TestMisquotationArtifacts:
    """check_draft attributes a quote to the nearest cite, and can miss.

    When the guess is wrong there is nothing to compare against, so the flag
    comes back with no closest passage and no diff — it records a failed
    attribution, not a misquotation. Observed on a filed brief: two of three
    misquotation flags were artifacts of exactly this shape, and reporting
    them would have put false findings on correctly quoted passages.
    """

    def test_flag_with_a_diff_is_a_real_comparison(self):
        assert misquotation_is_comparable(
            {"similarity": 0.606, "differences": ["- An", "+ a"],
             "closest_text": "An order refusing a motion"}) is True

    def test_flag_with_closest_text_only_is_real(self):
        assert misquotation_is_comparable(
            {"similarity": 0.9, "closest_text": "some passage"}) is True

    def test_failed_attribution_is_not_reported(self):
        assert misquotation_is_comparable(
            {"similarity": 0, "differences": None, "closest_text": None}) is False

    def test_artifacts_are_suppressed_and_counted(self):
        payload = {"summary": {}, "flags": [
            {"type": FLAG_MISQUOTATION, "similarity": 0,
             "differences": None, "closest_text": None},
            {"type": FLAG_MISQUOTATION, "similarity": 0.6,
             "differences": ["- a"], "closest_text": "real passage"},
        ]}
        review = CitationReview.from_check_draft(payload)
        assert len(review.findings) == 1
        assert review.suppressed == 1

    def test_unresolved_authority_is_reported_not_dropped(self):
        """Silently dropping a flag type is the failure this project avoids."""
        payload = {"summary": {}, "flags": [
            {"type": FLAG_UNRESOLVED_AUTHORITY, "cited_as": "N.D.C.C. 99-99-99",
             "draft_context": "see N.D.C.C. 99-99-99"}]}
        review = CitationReview.from_check_draft(payload)
        assert len(review.findings) == 1
        assert "does not resolve" in review.findings[0].headline


class TestParagraphAttribution:

    BRIEF = ("[¶ 9] Standard of review. State v. Reiswig, 2024 ND 153.\n"
             "\n[¶ 10] Findings must be adequate. State v. Juntunen, 2014 ND 86.\n")

    def test_context_maps_to_its_brief_paragraph(self):
        assert paragraph_for_context(self.BRIEF, "Findings must be adequate") == 10
        assert paragraph_for_context(self.BRIEF, "Standard of review") == 9

    def test_unlocatable_context_returns_none(self):
        assert paragraph_for_context("[¶ 1] text", "nothing like this at all") is None

    def test_empty_inputs(self):
        assert paragraph_for_context("", "x") is None
        assert paragraph_for_context("x", "") is None


class TestReviewFromCheckDraft:

    def test_real_finding_survives(self):
        review = CitationReview.from_check_draft(LIVE_PAYLOAD)
        assert FLAG_UNRESOLVED in [f.kind for f in review.findings]

    def test_bookkeeping_drift_is_suppressed_and_counted(self):
        review = CitationReview.from_check_draft(LIVE_PAYLOAD)
        assert FLAG_NAME_DRIFT not in [f.kind for f in review.findings]
        assert review.suppressed == 2
        assert "set aside" in review.coverage_line

    def test_findings_are_located_by_paragraph(self):
        brief = "[¶ 9] same as that of a motion to suppress. State v. Reiswig, 2024 ND 153."
        review = CitationReview.from_check_draft(LIVE_PAYLOAD, brief_text=brief)
        found = next(f for f in review.findings if f.kind == FLAG_UNRESOLVED)
        assert found.brief_paragraph == 9

    def test_coverage_states_what_was_checked(self):
        line = CitationReview.from_check_draft(LIVE_PAYLOAD).coverage_line
        assert "13 case citation(s) found, 7 resolved" in line
        assert "2 of 2 attributed quotation(s) verified" in line
        assert "not assessed" in line, "support must be disclaimed"
        assert "unverified, not confirmed" in line

    def test_out_of_scope_flags_are_ignored(self):
        """Treatment and currency are different questions."""
        payload = dict(LIVE_PAYLOAD)
        payload["flags"] = [
            {"severity": "S3", "type": "possible_negative_treatment"},
            {"severity": "S4", "type": "authority_currency"},
        ]
        assert CitationReview.from_check_draft(payload).findings == []

    def test_list_valued_cited_as_is_flattened(self):
        payload = {"summary": {}, "flags": [
            {"type": FLAG_UNRESOLVED, "cited_as": ["2024 ND 88", "1 N.W.3d 2"]}]}
        f = CitationReview.from_check_draft(payload).findings[0]
        assert f.cited_as == "2024 ND 88, 1 N.W.3d 2"

    def test_misquotation_carries_its_diff(self):
        payload = {"summary": {}, "flags": [{
            "type": FLAG_MISQUOTATION, "severity": "S1",
            "quote": "findings must permit meaningful review",
            "closest_text": "findings must permit appellate review",
            "differences": ["- meaningful", "+ appellate"]}]}
        f = CitationReview.from_check_draft(payload).findings[0]
        assert f.quote and f.closest_text
        assert "+ appellate" in f.differences


class TestReviewFromDict:

    def test_raw_check_draft_payload_is_recognised(self):
        review = CitationReview.from_dict(dict(LIVE_PAYLOAD, ndlaw_available=True))
        assert review.ndlaw_available is True
        assert review.findings

    def test_unavailable_says_so_rather_than_going_quiet(self):
        review = CitationReview.from_dict({"ndlaw_available": False})
        assert review.ndlaw_available is False
        assert "No citation was verified" in review.coverage_line
        assert "unverified, not confirmed" in review.coverage_line
        assert review.findings == []


class TestAdvisoryFirewall:
    """Citation findings must never move the recommendation."""

    def _review(self):
        return CitationReview(
            coverage_line="1 case citation(s) found, 0 resolved.",
            findings=[CitationFinding(
                kind=FLAG_UNRESOLVED, severity="S2", cited_as="2024 ND 999",
                context="see 2024 ND 999")])

    def test_finding_is_not_a_check_result(self):
        from core.models import CheckResult
        assert not isinstance(CitationFinding(kind=FLAG_UNRESOLVED), CheckResult)

    def test_report_keeps_the_review_out_of_results(self):
        report = ComplianceReport(
            brief_type=BriefType.APPELLANT,
            recommendation=Recommendation.ACCEPT,
            citation_review=self._review())
        assert report.results == []
        assert report.failed_checks == []
        assert report.recommendation == Recommendation.ACCEPT

    def test_hard_rule_recommendation_never_sees_citations(self):
        import importlib.util
        path = PROJECT_DIR / "skill" / "scripts" / "build_report.py"
        spec = importlib.util.spec_from_file_location("build_report", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rec, _ = module.compute_recommendation([])
        assert rec.value == "accept"

    def test_report_renders_the_advisory_banner(self):
        html = build_html_report(ComplianceReport(
            brief_type=BriefType.APPELLANT, recommendation=Recommendation.ACCEPT,
            citation_review=self._review()))
        flat = " ".join(html.split())
        assert "Citation Review" in html
        assert "not part of the compliance" in flat
        assert "does <strong>not</strong> assess whether an authority supports" in flat
        assert "2024 ND 999" in html

    def test_unavailable_review_still_renders_a_section(self):
        html = build_html_report(ComplianceReport(
            brief_type=BriefType.APPELLANT, recommendation=Recommendation.ACCEPT,
            citation_review=CitationReview.unavailable()))
        assert "Citation Review" in html
        assert "No citation was verified" in html

    def test_no_review_renders_no_section(self):
        """A run without the phase must not imply it happened."""
        html = build_html_report(ComplianceReport(
            brief_type=BriefType.APPELLANT, recommendation=Recommendation.ACCEPT))
        assert "Citation Review" not in html
