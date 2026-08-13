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

    def test_pinpoint_or_quotation_selects(self):
        scope = select_for_grounding([
            self._cite(pinpoint="9", start=1),
            self._cite(quotation="some quoted matter", start=2),
        ])
        assert len(scope.selected) == 2

    def test_bare_cite_is_low_value(self):
        scope = select_for_grounding([self._cite()])
        assert len(scope.low_value) == 1
        assert not scope.selected

    def test_quotations_outrank_pinpoints_under_the_cap(self):
        """A misquotation is the sharpest finding, so it must survive the cap."""
        cites = [self._cite(pinpoint="9", start=i) for i in range(DEFAULT_LOOKUP_CAP)]
        cites.append(self._cite(quotation="quoted matter here", start=999))
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
        cites = [self._cite(pinpoint="9", start=i) for i in range(DEFAULT_LOOKUP_CAP + 5)]
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
