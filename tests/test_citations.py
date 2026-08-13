"""Citation extraction and grounding scope.

This is the deterministic half of the citation-grounding pass: find the
citations, work out what each is offered for, and decide what is worth
retrieving.  Retrieval happens a level up, where ndlaw is reachable.

The design constraint that shapes everything here is that a citation which
was not checked must never read as one that was.  Every citation found lands
in exactly one bucket of ``GroundingScope`` so the coverage line accounts for
all of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "skill"))

from core.citations import (
    DEFAULT_LOOKUP_CAP,
    FOREIGN,
    ND_CASE,
    ND_RULE,
    ND_STATUTE,
    REGIONAL,
    Citation,
    extract_citations,
    select_for_grounding,
)


def _one(text: str, kind: str | None = None) -> Citation:
    cites = extract_citations(text)
    if kind:
        cites = [c for c in cites if c.kind == kind]
    assert cites, f"no citation extracted from {text!r}"
    return cites[0]


class TestCitationKinds:

    @pytest.mark.parametrize("text,kind,normalized", [
        ("Torgerson v. Bexley, 2024 ND 88", ND_CASE, "2024 ND 88"),
        # The Court of Appeals is a different court — "App" must survive
        ("In re K.B., 2019 ND App 12", ND_CASE, "2019 ND App 12"),
        ("Torgerson, 2024 ND 88", ND_CASE, "2024 ND 88"),
        ("N.D.C.C. § 14-09-06.2", ND_STATUTE, "N.D.C.C. § 14-09-06.2"),
        ("N.D.C.C. 14-09-06.2", ND_STATUTE, "N.D.C.C. § 14-09-06.2"),
        ("N.D.R.App.P. 32(a)(5)", ND_RULE, "N.D.R.App.P. 32(a)(5)"),
        ("N.D.R.Ct. 3.4(b)", ND_RULE, "N.D.R.Ct. 3.4(b)"),
    ])
    def test_kind_and_normalization(self, text, kind, normalized):
        cite = _one(text, kind)
        assert cite.kind == kind
        assert cite.normalized == normalized

    @pytest.mark.parametrize("text", [
        "Smith v. Jones, 501 U.S. 200 (1991)",
        "United States v. Doe, 123 F.3d 456",
        "State v. Roe, 88 P.3d 12",
    ])
    def test_foreign_authority_is_found_but_not_verifiable(self, text):
        cite = _one(text)
        assert cite.kind == FOREIGN
        assert cite.verifiable is False

    def test_nd_authority_is_verifiable(self):
        assert _one("2024 ND 88", ND_CASE).verifiable is True
        assert _one("N.D.C.C. § 14-09-06.2", ND_STATUTE).verifiable is True


class TestCourtOfAppeals:
    """"2019 ND App 12" and "2019 ND 12" are different cases."""

    def test_app_is_preserved(self):
        assert _one("2019 ND App 12", ND_CASE).normalized == "2019 ND App 12"

    def test_supreme_court_cite_is_distinct(self):
        assert _one("2019 ND 12", ND_CASE).normalized == "2019 ND 12"

    def test_the_two_do_not_collide(self):
        cites = extract_citations("Compare 2019 ND 12 with 2019 ND App 12.")
        assert {c.normalized for c in cites} == {"2019 ND 12", "2019 ND App 12"}


class TestParallelCitations:
    """One authority in two citation forms is one authority."""

    def test_regional_cite_folds_into_the_nd_cite(self):
        cites = extract_citations("Torgerson v. Bexley, 2024 ND 88, ¶ 9, 1002 N.W.2d 44.")
        assert len(cites) == 1, [c.raw for c in cites]
        assert cites[0].kind == ND_CASE
        assert cites[0].parallel_cite == "1002 N.W.2d 44"

    def test_folding_survives_a_pinpoint_between_the_two(self):
        cites = extract_citations("Halvorson, 2019 ND 12, ¶¶ 11-13, 921 N.W.2d 673.")
        assert len(cites) == 1
        assert cites[0].parallel_cite == "921 N.W.2d 673"

    def test_standalone_regional_cite_survives(self):
        """A pre-1997 ND decision has no medium-neutral form."""
        cites = extract_citations("Olson v. Olson, 445 N.W.2d 1 (N.D. 1989).")
        assert len(cites) == 1
        assert cites[0].kind == REGIONAL

    def test_distant_regional_cite_is_not_folded(self):
        text = "See 2024 ND 88 for the standard. A different case appears at 445 N.W.2d 1."
        kinds = [c.kind for c in extract_citations(text)]
        assert kinds.count(ND_CASE) == 1
        assert kinds.count(REGIONAL) == 1


class TestPinpoints:

    @pytest.mark.parametrize("text,pin", [
        ("2024 ND 88, ¶ 9", "9"),
        ("2024 ND 88, ¶¶ 9-11", "9-11"),
        ("2024 ND 88, para. 9", "9"),
        ("2024 ND 88, at ¶ 9", "9"),
    ])
    def test_case_pinpoint(self, text, pin):
        assert _one(text, ND_CASE).pinpoint == pin

    def test_statutory_subsection_is_the_pinpoint(self):
        assert _one("N.D.C.C. § 14-09-06.2(1)(d)", ND_STATUTE).pinpoint == "(1)(d)"

    def test_no_pinpoint(self):
        assert _one("2024 ND 88", ND_CASE).pinpoint is None


class TestProposition:
    """What the citation is offered to support."""

    def test_citation_sentence_takes_the_preceding_sentence(self):
        """A citation sentence asserts nothing; the sentence before it does."""
        text = ("Findings are reviewed for clear error. "
                "Torgerson v. Bexley, 2024 ND 88, ¶ 9, 1002 N.W.2d 44.")
        assert _one(text, ND_CASE).proposition == "Findings are reviewed for clear error."

    def test_embedded_citation_keeps_its_own_sentence(self):
        text = "In Halvorson, 2019 ND 12, ¶ 11, this Court required adequate findings."
        prop = _one(text, ND_CASE).proposition
        assert "required adequate findings" in prop

    def test_signal_only_sentence_still_looks_back(self):
        text = "The factors are mandatory. See N.D.C.C. § 14-09-06.2."
        assert _one(text, ND_STATUTE).proposition == "The factors are mandatory."

    def test_case_name_does_not_split_the_sentence(self):
        """"v." must not read as a sentence end — it truncated the proposition."""
        text = ("The court in Torgerson v. Bexley applied the clearly erroneous "
                "standard to these findings. 2024 ND 88, ¶ 9.")
        prop = _one(text, ND_CASE).proposition
        assert "clearly erroneous standard" in prop

    def test_paragraph_marker_is_stripped(self):
        text = "[14] The findings were inadequate. Halvorson, 2019 ND 12, ¶ 11."
        assert not _one(text, ND_CASE).proposition.startswith("[14]")


class TestQuotationAttribution:

    def test_quotation_before_the_citation(self):
        text = 'The court held that "findings must permit review." Halvorson, 2019 ND 12, ¶ 11.'
        assert _one(text, ND_CASE).quotation == "findings must permit review."

    def test_quotation_after_the_citation(self):
        text = 'Halvorson, 2019 ND 12, ¶ 11 ("findings must permit meaningful review").'
        assert "meaningful review" in (_one(text, ND_CASE).quotation or "")

    def test_quotation_does_not_cross_paragraphs(self):
        """The regression: one paragraph's quotation reached every citation."""
        text = (
            '[1] The court held that "findings must permit review." Halvorson, 2019 ND 12, ¶ 11.\n'
            '\n[2] The standard of review is settled. Torgerson, 2024 ND 88, ¶ 9.\n'
        )
        cites = {c.normalized: c for c in extract_citations(text)}
        assert cites["2019 ND 12"].quotation is not None
        assert cites["2024 ND 88"].quotation is None


class TestAntecedentName:

    def test_case_name_captured(self):
        assert _one("Torgerson v. Bexley, 2024 ND 88", ND_CASE).antecedent_name == \
            "Torgerson v. Bexley"

    def test_signal_is_not_part_of_the_name(self):
        name = _one("See Torgerson v. Bexley, 2024 ND 88", ND_CASE).antecedent_name
        assert name == "Torgerson v. Bexley"

    def test_absent_name(self):
        assert _one("The rule appears at 2024 ND 88, ¶ 9", ND_CASE).antecedent_name is None


class TestParagraphAttribution:

    def test_citation_maps_to_its_brief_paragraph(self):
        text = "[12] First point. 2024 ND 88, ¶ 9.\n\n[13] Second point. 2019 ND 12, ¶ 4.\n"
        cites = {c.normalized: c for c in extract_citations(text)}
        assert cites["2024 ND 88"].paragraph == 12
        assert cites["2019 ND 12"].paragraph == 13


class TestGroundingScope:

    def _cite(self, kind=ND_CASE, pinpoint=None, quotation=None, start=0):
        return Citation(raw="x", kind=kind, start=start, end=start + 1,
                        pinpoint=pinpoint, quotation=quotation)

    def test_foreign_authority_is_unverifiable(self):
        scope = select_for_grounding([self._cite(kind=FOREIGN, pinpoint="9")])
        assert len(scope.unverifiable) == 1
        assert not scope.selected

    def test_every_nd_authority_is_selected(self):
        """Existence needs no pinpoint, so nothing is skipped for lacking one."""
        scope = select_for_grounding([
            Citation(raw="a", kind=ND_CASE, start=1, end=2, normalized="2024 ND 1"),
            Citation(raw="b", kind=ND_CASE, start=3, end=4, normalized="2024 ND 2",
                     quotation="some quoted matter"),
        ])
        assert len(scope.selected) == 2
        assert len(scope.quotations) == 1

    def test_bare_cite_is_still_checked(self):
        """Existence needs no pinpoint, so a bare cite is worth verifying."""
        scope = select_for_grounding([self._cite()])
        assert len(scope.selected) == 1

    def test_repeat_citation_of_one_authority_is_deduped(self):
        """Existence is a property of the authority, not the occurrence."""
        scope = select_for_grounding([
            Citation(raw="2024 ND 88", kind=ND_CASE, start=1, end=2,
                     normalized="2024 ND 88"),
            Citation(raw="2024 ND 88", kind=ND_CASE, start=9, end=10,
                     normalized="2024 ND 88"),
        ])
        assert len(scope.selected) == 1
        assert len(scope.duplicate) == 1
        assert scope.total == 2

    def test_repeat_citation_carrying_its_own_quotation_is_still_verified(self):
        """The authority is checked once; each quotation is checked separately."""
        scope = select_for_grounding([
            Citation(raw="2024 ND 88", kind=ND_CASE, start=1, end=2,
                     normalized="2024 ND 88"),
            Citation(raw="2024 ND 88", kind=ND_CASE, start=9, end=10,
                     normalized="2024 ND 88", quotation="a quoted passage here"),
        ])
        assert len(scope.selected) == 1, "one authority, one existence check"
        assert len(scope.quotations) == 1, "the quotation is still verified"
        assert scope.total == 2

    def test_subsection_does_not_split_an_authority(self):
        """"N.D.R.Ev. 201" and "201(b)" are one rule, not two."""
        scope = select_for_grounding([
            Citation(raw="a", kind=ND_RULE, start=1, end=2, normalized="N.D.R.Ev. 201"),
            Citation(raw="b", kind=ND_RULE, start=5, end=6,
                     normalized="N.D.R.Ev. 201(b)", pinpoint="(b)"),
        ])
        assert len(scope.selected) == 1
        assert len(scope.duplicate) == 1

    def test_quotations_outrank_bare_cites_under_the_cap(self):
        """A misquotation is the sharper finding, so it must survive the cap."""
        cites = [Citation(raw=f"c{i}", kind=ND_CASE, start=i, end=i + 1,
                          normalized=f"20{i:02d} ND {i}")
                 for i in range(DEFAULT_LOOKUP_CAP)]
        cites.append(Citation(raw="q", kind=ND_CASE, start=999, end=1000,
                              normalized="2099 ND 99", quotation="quoted matter here"))
        scope = select_for_grounding(cites)
        assert any(c.quotation for c in scope.selected)
        assert len(scope.selected) == DEFAULT_LOOKUP_CAP

    def test_every_citation_is_accounted_for(self):
        """The coverage line must add up — nothing may vanish."""
        cites = [self._cite(kind=FOREIGN, start=1),
                 self._cite(pinpoint="9", start=2),
                 self._cite(start=3)]
        scope = select_for_grounding(cites)
        assert scope.total == 3

    def test_cap_excess_is_reported_not_dropped(self):
        cites = [Citation(raw=f"c{i}", kind=ND_CASE, start=i, end=i + 1,
                          normalized=f"20{i:02d} ND {i}")
                 for i in range(DEFAULT_LOOKUP_CAP + 5)]
        scope = select_for_grounding(cites)
        assert len(scope.selected) == DEFAULT_LOOKUP_CAP
        assert len(scope.over_cap) == 5
        assert "beyond the" in scope.coverage_line()

    def test_coverage_line_refuses_to_imply_confirmation(self):
        scope = select_for_grounding([self._cite(kind=FOREIGN)])
        line = scope.coverage_line()
        assert "unverified, not confirmed" in line
        assert "not checked" in line

    def test_empty_brief(self):
        scope = select_for_grounding([])
        assert scope.total == 0
        assert "Found 0 citation(s)" in scope.coverage_line()


# ===================================================================
# Review results and their firewall from the recommendation
# ===================================================================

from core.citations import (  # noqa: E402
    COULD_NOT_RETRIEVE,
    DOES_NOT_SUPPORT,
    EXISTS_CONFIRMED,
    EXISTS_NOT_FOUND,
    PARTIALLY_SUPPORTS,
    QUOTE_ALTERED,
    QUOTE_NOT_FOUND,
    QUOTE_VERBATIM,
    SUPPORTS,
    CitationFinding,
    CitationReview,
)


class TestFindingFlags:
    """Which outcomes deserve a reader's attention."""

    def test_sound_citation_is_not_flagged(self):
        f = CitationFinding(cite="2024 ND 88", exists=EXISTS_CONFIRMED,
                            name_matches=True, support=SUPPORTS)
        assert f.flagged is False

    @pytest.mark.parametrize("kwargs", [
        {"exists": EXISTS_NOT_FOUND},
        {"name_matches": False},
        {"quotation_result": QUOTE_ALTERED},
        {"quotation_result": QUOTE_NOT_FOUND},
    ])
    def test_defects_are_flagged(self, kwargs):
        assert CitationFinding(cite="x", **kwargs).flagged is True

    def test_wrong_name_on_a_real_cite_is_flagged(self):
        """The authority exists — it is just not the one the brief names."""
        f = CitationFinding(cite="2024 ND 88", exists=EXISTS_CONFIRMED,
                            name_matches=False, antecedent_name="Wrong v. Case")
        assert f.flagged is True

    def test_could_not_retrieve_is_not_a_finding(self):
        """A failed lookup is not evidence against the brief."""
        f = CitationFinding(cite="x", exists=EXISTS_CONFIRMED,
                            support=COULD_NOT_RETRIEVE)
        assert f.flagged is False

    @pytest.mark.parametrize("support", [PARTIALLY_SUPPORTS, DOES_NOT_SUPPORT])
    def test_support_is_out_of_scope_and_never_flags(self, support):
        """Nothing populates `support`; it must not gate anything either."""
        f = CitationFinding(cite="x", exists=EXISTS_CONFIRMED, support=support)
        assert f.flagged is False

    def test_verbatim_quotation_is_not_flagged(self):
        assert CitationFinding(cite="x", quotation_result=QUOTE_VERBATIM).flagged is False


class TestCitationReview:

    def test_unavailable_says_so_rather_than_going_quiet(self):
        review = CitationReview.unavailable("ndlaw not configured")
        assert review.ndlaw_available is False
        assert "No citation was verified" in review.coverage_line
        assert "unverified, not confirmed" in review.coverage_line

    def test_round_trips_through_json(self):
        payload = {
            "ndlaw_available": True,
            "coverage_line": "Found 3 citation(s); 2 selected for verification.",
            "findings": [
                {"cite": "2024 ND 88", "exists": "confirmed", "support": "supports"},
                {"cite": "2019 ND 12", "quotation_result": "altered",
                 "reason": "wording differs"},
            ],
        }
        review = CitationReview.from_dict(payload)
        assert len(review.findings) == 2
        assert len(review.flagged) == 1
        assert len(review.clear) == 1

    def test_unavailable_round_trips(self):
        review = CitationReview.from_dict({"ndlaw_available": False})
        assert review.ndlaw_available is False
        assert review.findings == []

    def test_missing_fields_default_to_unchecked(self):
        """A sparse record must not read as a confirmed one."""
        f = CitationFinding.from_dict({"cite": "2024 ND 88"})
        assert f.exists == "unchecked"
        assert f.support == "not_assessed"
        assert f.flagged is False


class TestAdvisoryFirewall:
    """Citation findings must never move the recommendation."""

    def test_review_is_not_a_check_result(self):
        """Routing findings through `results` would let them score."""
        from core.models import CheckResult
        assert not isinstance(CitationFinding(cite="x"), CheckResult)

    def test_report_keeps_the_review_out_of_results(self):
        from core.models import BriefType, ComplianceReport, Recommendation
        review = CitationReview(findings=[
            CitationFinding(cite="2024 ND 88", quotation_result=QUOTE_ALTERED)])
        report = ComplianceReport(
            brief_type=BriefType.APPELLANT,
            recommendation=Recommendation.ACCEPT,
            citation_review=review,
        )
        assert report.results == []
        assert report.failed_checks == []
        assert report.recommendation == Recommendation.ACCEPT

    def test_hard_rule_recommendation_never_sees_citations(self):
        """Even a brief whose every citation is unsupported stays ACCEPT."""
        import importlib.util
        path = PROJECT_DIR / "skill" / "scripts" / "build_report.py"
        spec = importlib.util.spec_from_file_location("build_report", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rec, _ = module._hard_rule_recommendation([])
        assert rec.value == "accept"

    def test_report_renders_the_advisory_banner(self):
        from core.models import BriefType, ComplianceReport, Recommendation
        from core.report_builder import build_html_report
        review = CitationReview(
            coverage_line="Found 1 citation(s); 1 selected for verification.",
            findings=[CitationFinding(cite="2024 ND 88", quotation_result=QUOTE_ALTERED,
                                      reason="wording differs from the opinion")])
        html = build_html_report(ComplianceReport(
            brief_type=BriefType.APPELLANT, recommendation=Recommendation.ACCEPT,
            citation_review=review))
        assert "Citation Review" in html
        assert "not part of the compliance" in html
        # whitespace-independent: the banner wraps mid-sentence
        flat = " ".join(html.split())
        assert "does <strong>not</strong> assess whether an authority supports" in flat

    def test_unavailable_review_still_renders_a_section(self):
        from core.models import BriefType, ComplianceReport, Recommendation
        from core.report_builder import build_html_report
        html = build_html_report(ComplianceReport(
            brief_type=BriefType.APPELLANT, recommendation=Recommendation.ACCEPT,
            citation_review=CitationReview.unavailable()))
        assert "Citation Review" in html
        assert "were not" in html and "available" in html

    def test_no_review_renders_no_section(self):
        """A run without the phase must not imply it happened."""
        from core.models import BriefType, ComplianceReport, Recommendation
        from core.report_builder import build_html_report
        html = build_html_report(ComplianceReport(
            brief_type=BriefType.APPELLANT, recommendation=Recommendation.ACCEPT))
        assert "Citation Review" not in html


class TestNameDriftCalibration:
    """Calibrated against a live ndlaw run, not intuition.

    ndlaw compares the name as written against a canonical short form, so a
    correct citation in a longer style scores well below 1.0. A real brief
    citing "Davis o/b/o HJR & CER v. Romanyshyn" scored 0.667 against the
    canonical "Davis, et al. v. Romanyshyn" — the same case, correctly cited.
    Flagging on any mismatch would have reported that as an error.
    """

    def test_stylistic_variance_is_not_flagged(self):
        f = CitationFinding(
            cite="2025 ND 18", exists=EXISTS_CONFIRMED, name_matches=False,
            name_similarity=0.667,
            antecedent_name="Davis o/b/o HJR & CER v. Romanyshyn",
            canonical_name="Davis, et al. v. Romanyshyn")
        assert f.name_drifted is False
        assert f.flagged is False

    def test_a_genuinely_different_case_is_flagged(self):
        f = CitationFinding(cite="2024 ND 88", exists=EXISTS_CONFIRMED,
                            name_matches=False, name_similarity=0.12,
                            antecedent_name="Smith v. Jones",
                            canonical_name="Torgerson v. Bexley")
        assert f.name_drifted is True
        assert f.flagged is True

    def test_mismatch_without_a_score_is_flagged(self):
        """No similarity reported — raise it rather than assume it is style."""
        f = CitationFinding(cite="x", name_matches=False)
        assert f.name_drifted is True


class TestExtractionAgainstRealBriefPatterns:
    """Shapes taken from a live run over a filed brief.

    Each of these was wrong at some point during that run, and each error
    would have produced a false flag against a correctly drafted brief.
    """

    def test_name_does_not_swallow_the_preceding_sentence(self):
        """A widened token set plus IGNORECASE let names absorb prose."""
        text = ("This Court cannot properly review a decision if the district "
                "court fails to make adequate findings. State v. Juntunen, "
                "2014 ND 86, ¶ 3, 845 N.W.2d 325.")
        assert _one(text, ND_CASE).antecedent_name == "State v. Juntunen"

    def test_connectors_survive_in_a_party_name(self):
        text = "Davis o/b/o HJR & CER v. Romanyshyn, 2025 ND 18, ¶ 11."
        assert _one(text, ND_CASE).antecedent_name == "Davis o/b/o HJR & CER v. Romanyshyn"

    def test_quotation_attaches_to_the_citation_that_follows_it(self):
        """A quote introduces the cite after it, not the one before."""
        text = (
            "[10] Findings must be adequate. State v. Juntunen, 2014 ND 86, ¶ 3.\n"
            "“A court’s findings are adequate if this Court is able to discern the "
            "factual basis for the decision.” State v. P.K., 2020 ND 235, ¶ 15.\n"
        )
        cites = {c.normalized: c for c in extract_citations(text)}
        assert cites["2014 ND 86"].quotation is None
        assert "adequate" in (cites["2020 ND 235"].quotation or "")

    def test_parenthetical_quotation_still_attaches_backwards(self):
        text = 'Koon v. State, 2023 ND 247, ¶ 11 (“an arbitrary or unreasonable manner”).'
        assert "arbitrary" in (_one(text, ND_CASE).quotation or "")

    def test_page_number_inside_a_quotation_is_dropped(self):
        """Extraction interleaves page numbers; ndlaw would read it as altered."""
        text = ('“A court’s findings afford a clear understanding of \n\n8 \n\nits '
                'decision.” State v. P.K., 2020 ND 235, ¶ 15.')
        quote = _one(text, ND_CASE).quotation
        assert quote is not None
        assert " 8 " not in quote
        assert "understanding of its decision" in quote

    def test_bracketed_paragraph_marker_is_recognised(self):
        """Real briefs number paragraphs "[¶ 10]", not only "[10]"."""
        text = "[¶ 10] Findings must be adequate. State v. Juntunen, 2014 ND 86, ¶ 3."
        assert _one(text, ND_CASE).paragraph == 10
