"""Semantic check definitions — pure data, no third-party imports.

Separated from ``checks_semantic`` so that consumers which must not depend
on the ``anthropic`` SDK can read the inventory.  ``skill/requirements.txt``
installs only PyMuPDF, so in a deployed skill ``import anthropic`` fails;
``build_report.py`` needs this list to reconcile the semantic results it is
handed against the checks that were supposed to run.

Tuple shape: (check_id, name, rule, applicable_types, severity, description)
where ``applicable_types`` of None means every brief type.
"""

from __future__ import annotations

from core.models import BriefType, CheckResult, Severity


SEMANTIC_CHECKS = [
    # Rule 28(b)(1): "a table of contents, with paragraph references"
    ("SEC-001", "Table of Contents Present", "28(b)(1)",
     None, Severity.REJECT, "Brief must contain a Table of Contents."),
    ("SEC-002", "TOC Uses Paragraph References", "28(b)(1)",
     None, Severity.CORRECTION,
     "Table of Contents must use paragraph references, not page numbers alone."),

    # Rule 28(b)(2): "a table of authorities—cases (alphabetically arranged)...with references to the paragraphs"
    ("SEC-003", "Table of Authorities Present", "28(b)(2)",
     None, Severity.REJECT, "Brief must contain a Table of Authorities."),
    ("SEC-004", "TOA: Cases Alphabetical, Paragraph Refs", "28(b)(2)",
     None, Severity.CORRECTION,
     "Table of Authorities must list cases alphabetically with paragraph references."),

    # Rule 28(b)(3): original jurisdiction statement (not general jurisdictional statement)
    ("SEC-005", "Jurisdictional Statement", "28(b)(3)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "In an original jurisdiction application, appellant must include a jurisdictional statement."),

    # Rule 28(b)(4): "a statement of the issues presented for review"
    ("SEC-006", "Statement of Issues", "28(b)(4)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Statement of the Issues presented for review."),

    # Rule 28(b)(5): "a statement of the case briefly indicating the nature of the case..."
    ("SEC-007", "Statement of the Case", "28(b)(5)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant brief must include a Statement of the Case (procedural history)."),

    # Rule 28(b)(6): "a statement of the facts relevant to the issues...with appropriate references to the record"
    ("SEC-008", "Statement of Facts with Record References", "28(b)(6)",
     [BriefType.APPELLANT], Severity.REJECT,
     "Appellant brief must include a Statement of Facts with record references."),

    # Rule 28(b)(7): "the argument"
    ("SEC-009", "Argument Section Present", "28(b)(7)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.AMICUS,
      BriefType.AMICUS_REHEARING], Severity.REJECT,
     "Brief must contain an Argument section."),

    # Rule 28(b)(7)(B)(i): "a concise statement of the applicable standard of review"
    ("SEC-010", "Standard of Review Stated", "28(b)(7)(B)(i)",
     [BriefType.APPELLANT], Severity.CORRECTION,
     "Appellant must state the applicable standard of review for each issue."),

    # Rule 28(b)(7)(B)(ii): "citation to the record showing that the issue was preserved for review"
    ("SEC-011", "Preservation Citations", "28(b)(7)(B)(ii)",
     [BriefType.APPELLANT], Severity.NOTE,
     "Appellant must cite where each issue was preserved for review in the record."),

    # Rule 28(b)(7)(D): "a short conclusion stating the precise relief sought"
    ("SEC-012", "Conclusion with Precise Relief", "28(b)(7)(D)",
     [BriefType.APPELLANT, BriefType.APPELLEE], Severity.CORRECTION,
     "Brief must include a Conclusion stating the precise relief sought."),

    # Rule 29(a)(4)(C): "a concise statement of the identity of the amicus curiae, and its interest in the case"
    ("SEC-014", "Amicus: Identity/Interest Statement", "29(a)(4)(C)",
     [BriefType.AMICUS, BriefType.AMICUS_REHEARING], Severity.REJECT,
     "Amicus brief must include a statement of identity and interest."),

    # Rule 29(a)(4)(D): disclosure of authorship and funding
    ("SEC-015", "Amicus: Disclosure Statement", "29(a)(4)(D)",
     [BriefType.AMICUS, BriefType.AMICUS_REHEARING], Severity.CORRECTION,
     "Amicus brief must include a disclosure statement (authorship and funding)."),

    # Rule 28(e): "counsel should use the parties' actual names or the designations used in the lower court"
    ("CNT-001", "Party References Use Actual Names", "28(e)",
     None, Severity.CORRECTION,
     "Parties should be referred to by actual names, not procedural labels like 'Appellant.'"),

    # Rule 28(l): "must be concise...free from burdensome, irrelevant or immaterial matters"
    ("CNT-002", "Brief Is Concise, No Irrelevant Matter", "28(l)",
     None, Severity.NOTE,
     "Brief must be concise and free of irrelevant, immaterial, or scandalous matter."),

    # Rule 28(g): "the relevant parts must be set out in the brief or in an addendum"
    ("CNT-003", "Statutes/Rules in Brief or Addendum", "28(g)",
     None, Severity.NOTE,
     "Pertinent statutes and rules must be set forth in the brief or addendum."),

    # Rule 28(f)(2), effective Sept. 1, 2026: "A party may not incorporate by
    # reference the contents of a brief filed elsewhere or in another case."
    # Gated to party briefs — an amicus is not a party.
    ("CNT-005", "No Incorporation by Reference", "28(f)(2)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.REPLY,
      BriefType.CROSS_APPEAL, BriefType.PETITION_REHEARING], Severity.CORRECTION,
     "A party may not incorporate by reference a brief filed elsewhere or in another case."),

    # Rule 30(b)(1): record citations should use (R{index}:{page}) format
    ("REC-002", "Record Citation Format", "30(b)(1)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL], Severity.CORRECTION,
     "Record citations should use the (R{index}:{page}) format per Rule 30(b)(1)."),

    # Rule 30(a): record references should identify the item cited
    ("REC-003", "Record Citations Identify Items", "30(a)",
     [BriefType.APPELLANT, BriefType.APPELLEE, BriefType.CROSS_APPEAL], Severity.NOTE,
     "Record references should include information identifying the item cited, e.g. 'Statement of John Doe.'"),

    # N.D.R.Ct. 3.4(b)(1)(C) / Rule 14(a)(5): minors identified by initials
    ("PRV-001", "Privacy: Minor Names Redacted", "N.D.R.Ct. 3.4(b)(1)(C)",
     None, Severity.CORRECTION,
     "Individuals known to be minors must be identified by initials only."),

    # Rule 14(a)(1): mental health respondent identity protection
    ("PRV-002", "Identity Protection: Mental Health Respondent", "14(a)(1)",
     None, Severity.CORRECTION,
     "Mental health respondents must be referred to by initials only."),

    # Rule 14(a)(2): guardianship/conservatorship identity protection
    ("PRV-003", "Identity Protection: Guardianship/Conservatorship", "14(a)(2)",
     None, Severity.CORRECTION,
     "Respondent and family members in guardianship/conservatorship must use initials."),

    # Rule 14(a)(3): juvenile respondent identity protection
    ("PRV-004", "Identity Protection: Juvenile Respondent", "14(a)(3)",
     None, Severity.CORRECTION,
     "Juvenile respondents must be referred to by initials."),

    # Rule 14(a)(4): TPR proceedings identity protection
    ("PRV-005", "Identity Protection: TPR Proceedings", "14(a)(4)",
     None, Severity.CORRECTION,
     "Child and family members in TPR proceedings must use initials."),

    # Rule 14(a)(6): sexual offense victim identity protection
    ("PRV-006", "Identity Protection: Sexual Offense Victim", "14(a)(6)",
     None, Severity.CORRECTION,
     "Sexual offense victims must be referred to by initials."),

    # Rule 21(a)(2): writ petition required content
    ("WRT-001", "Writ Petition: Required Content", "21(a)(2)",
     None, Severity.CORRECTION,
     "Writ petition must state relief sought, issues, facts, and reasons."),

    # Rule 21(a)(3): writ petition supporting documents
    ("WRT-002", "Writ Petition: Supporting Documents", "21(a)(3)",
     None, Severity.CORRECTION,
     "Writ petition must attach necessary documents not in a related district court record as exhibits."),

    # Rule 21(a)(3)(B), (D): exhibit citation format (mandatory since Sept. 1, 2026)
    ("WRT-003", "Writ Petition: Exhibit Citation Format", "21(a)(3)(B)",
     None, Severity.CORRECTION,
     "Exhibits must be cited as (E{exhibit}:{page}), naming the document on first reference."),

    # Rule 40(a)(2): petition for rehearing must state overlooked/misapprehended points
    ("RHR-001", "Rehearing: Points Overlooked or Misapprehended", "40(a)(2)",
     [BriefType.PETITION_REHEARING], Severity.REJECT,
     "Petition must state with particularity each point of law or fact the court overlooked or misapprehended."),

    # Rule 40(b): petition must include applicable items from Rule 28(b)
    ("RHR-002", "Rehearing: Applicable Rule 28(b) Items", "40(b)",
     [BriefType.PETITION_REHEARING], Severity.CORRECTION,
     "Petition must include applicable items required under Rule 28(b) (e.g., TOC, TOA)."),

    # Rule 40(a)(2): supporting argument present
    ("RHR-003", "Rehearing: Supporting Argument", "40(a)(2)",
     [BriefType.PETITION_REHEARING], Severity.REJECT,
     "Petition must contain argument in support of the petition."),

    # N.D.R.Ct. 11.6: medium-neutral citation compliance (semantic)
    ("CIT-002", "ND Case Citations: Pre/Post-1997 Compliance", "N.D.R.Ct. 11.6",
     None, Severity.NOTE,
     "Claude evaluates whether pre-1997 vs post-1997 citation distinction is correctly applied."),
]


def gated_check_result(
    check_id: str,
    name: str,
    rule: str,
    severity: Severity,
    brief_type: BriefType,
) -> CheckResult:
    """Result for a check whose brief type filtered it out.

    Two different things wear the same shape, and only one of them is a
    genuine exclusion:

    * **Not applicable.** The brief type is known and the check does not
      reach it — an amicus disclosure requirement on an appellant brief.
      Nothing is owed, so nothing is unverified.
    * **Not determined.** The brief type is UNKNOWN, so the check was
      skipped for want of a classification, not because it does not apply.
      A brief does not stop needing a Statement of Issues because the cover
      could not be read. Ten checks are gated this way, three of them at
      REJECT severity, so labelling them "not applicable" tells the reader
      they were correctly excluded when they were never run.

    Both carry ``applicable=False`` and stay out of the recommendation; they
    differ in what the report says happened.
    """
    if brief_type == BriefType.UNKNOWN:
        return CheckResult(
            check_id=check_id, name=name, rule=rule,
            passed=False, severity=severity, applicable=False,
            message="Not determined — brief type could not be identified, so "
                    "this type-specific check was not run.",
            details="This check may well apply to the brief; it was skipped "
                    "for want of a classification. Re-run with the brief type "
                    "supplied to evaluate it.",
        )
    return CheckResult(
        check_id=check_id, name=name, rule=rule,
        passed=True, severity=severity, applicable=False,
        message=f"Not applicable to {brief_type.value} briefs.",
    )
