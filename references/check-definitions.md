# Brief Compliance Check Definitions

All citations verified against the Iowa Rules of Appellate Procedure.

## Mechanical Checks (Deterministic)

These are run by `check_brief.py` — no changes needed here.

| ID | Check | Rule | Failed Severity |
|---|---|---|---|
| FMT-001 | Paper size 8.5 x 11" | 6.903(1)(d) | REJECT |
| FMT-002 | Left margin >= 1" | 6.903(1)(d) | REJECT |
| FMT-003 | Right margin >= 1" | 6.903(1)(d) | CORRECTION |
| FMT-004 | Top margin >= 1" | 6.903(1)(d) | CORRECTION |
| FMT-005 | Bottom margin >= 1" (excluding page numbers) | 6.903(1)(d) | CORRECTION |
| FMT-006 | Font size >= 14pt (proportional) or <= 10.5 cpi (mono) | 6.903(1)(e) | REJECT |
| FMT-008 | Plain roman style | 6.903(1)(f) | NOTE |
| FMT-009 | Double-spaced body text | 6.903(1)(d) | CORRECTION |
| FMT-010 | Footnotes same typeface as text | 6.903(1)(e) | NOTE |
| FMT-011 | Pages numbered consecutively | 6.903(1)(d) | CORRECTION |
| WC-001 | Principal brief <= 14,000 words | 6.903(1)(g)(1) | REJECT |
| WC-002 | Reply brief <= 7,000 words | 6.903(1)(g)(1) | REJECT |
| WC-003 | Amicus brief <= 7,000 words | 6.906(4) | REJECT |
| SEC-013 | Certificate of Compliance present | 6.903(1)(i) | CORRECTION |
| REC-001 | Record citations present (App. pp. ___) format | 6.904(2) | NOTE |

## Semantic Checks (Claude Code Evaluation)

These checks are evaluated by Claude Code during the skill workflow.

### Applicability by Brief Type

Before evaluating, filter checks by brief type:
- **All types**: SEC-001 through SEC-004, SEC-013, SEC-019, CNT-001, CNT-002, CNT-003
- **Appellant only**: SEC-006, SEC-006A, SEC-016, SEC-007, SEC-008, SEC-010, SEC-017
- **Appellant + Appellee + Amicus**: SEC-009
- **Appellant + Appellee**: SEC-012, SEC-018
- **Appellant + Appellee + Cross-appeal**: REC-002, REC-003
- **Amicus only**: SEC-014, SEC-015

If a check is not applicable to the brief type, mark it as `"passed": true, "applicable": false`.

### Evaluation Guidance

#### SEC-001 — Table of Contents Present
**Rule**: 6.903(2)(1) — requires a table of contents with page references
**Pass if**: A TOC section exists with section headings listed.
**Fail if**: No TOC is present at all.
**Severity**: REJECT

#### SEC-002 — TOC Uses Page References
**Rule**: 6.903(2)(1) — requires page references
**Look for**: Whether the TOC entries include page numbers. Iowa uses page references (not paragraph references).
**Pass if**: TOC entries include page references.
**Fail if**: TOC entries have no page references.
**Severity**: CORRECTION

#### SEC-003 — Table of Authorities Present
**Rule**: 6.903(2)(2) — requires a table of authorities with page references
**Pass if**: A TOA section exists listing authorities.
**Fail if**: No TOA section is found.
**Severity**: REJECT

#### SEC-004 — TOA: Cases Alphabetical, Page Refs
**Rule**: 6.903(2)(2)
**Pass if**: Cases appear alphabetical and references include page numbers.
**Fail if**: Cases are not alphabetical, or references lack page numbers.
**Severity**: CORRECTION

#### SEC-006 — Statement of Issues
**Rule**: 6.903(2)(3) — requires a statement of the issues presented for review
**Pass if**: An issues section exists with identifiable legal questions.
**Fail if**: No issues section is found.
**Severity**: REJECT

#### SEC-006A — Issues Include Preservation & Authority Citations
**Rule**: 6.903(2)(3) — each issue must include a preservation citation and the most apposite authority
**Pass if**: Each issue includes a citation to where it was preserved AND the most apposite authority.
**Fail if**: Issues lack preservation citations or authority citations.
**Severity**: CORRECTION

#### SEC-016 — Routing Statement
**Rule**: 6.903(2)(4) — requires a routing statement
**Look for**: A section labeled "Routing Statement" or similar that indicates whether the case should be retained by the Supreme Court or transferred to the Court of Appeals, referencing the criteria in Iowa R. App. P. 6.1101(2) and (3).
**Pass if**: A routing statement is present.
**Fail if**: No routing statement found. This is an Iowa-specific requirement.
**Severity**: REJECT

#### SEC-007 — Statement of the Case
**Rule**: 6.903(2)(5) — requires a statement of the case (nature, proceedings, disposition)
**Pass if**: A procedural history / statement of the case section exists.
**Fail if**: No such section is found.
**Severity**: CORRECTION

#### SEC-008 — Statement of Facts with Record References
**Rule**: 6.903(2)(6) — requires a statement of facts with record references (Rule 6.904)
**Look for**: A Statement of Facts section with citations like (App. pp. ___), (Tr. p. ___), etc.
**Pass if**: Facts section exists AND contains record references.
**Fail if**: No facts section, OR facts section lacks record references.
**Severity**: REJECT

#### SEC-009 — Argument Section Present
**Rule**: 6.903(2)(7)
**Pass if**: An argument section with legal analysis is present.
**Fail if**: No argument section found.
**Severity**: REJECT

#### SEC-010 — Standard/Scope of Review Stated
**Rule**: 6.903(2)(7) — requires a scope or standard of review for each issue
**Look for**: Standard of review language (e.g., "de novo", "substantial evidence", "abuse of discretion", "for correction of errors at law").
**Pass if**: Standard of review is stated for each argument division.
**Fail if**: No standard of review language found.
**Severity**: CORRECTION

#### SEC-017 — Preservation of Error
**Rule**: 6.903(2)(7) — requires a statement of how each issue was preserved
**Look for**: In the argument section, statements of how each issue was raised and decided in district court, with record references.
**Pass if**: Preservation of error is addressed for each issue.
**Fail if**: No preservation language found.
**Note**: This is a key Iowa requirement — error preservation must appear in the argument for each issue.
**Severity**: CORRECTION

#### SEC-012 — Conclusion with Precise Relief
**Rule**: 6.903(2)(8) — requires a conclusion stating the precise relief sought
**Pass if**: Conclusion exists and states specific relief (e.g., "reverse and remand", "affirm").
**Fail if**: No conclusion, or conclusion is vague.
**Severity**: CORRECTION

#### SEC-018 — Request for Oral Argument
**Rule**: 6.903(2)(9) — requires a request for oral argument or waiver
**Pass if**: Brief includes a request for oral argument or states argument is waived.
**Fail if**: Neither a request nor a waiver is present.
**Severity**: NOTE

#### SEC-013 — Certificate of Compliance
**Rule**: 6.903(1)(i) — requires Form 7 certificate
**Pass if**: A certificate of compliance section is present.
**Fail if**: Missing.
**Severity**: CORRECTION

#### SEC-019 — Certificate of Filing/Service
**Rule**: 6.903(2)(11) — requires a certificate of filing and service
**Pass if**: A certificate of filing/service is present.
**Fail if**: Missing.
**Severity**: CORRECTION

#### SEC-014 — Amicus: Identity/Interest Statement
**Rule**: 6.906(3)
**Pass if**: Identity and interest statement is present.
**Fail if**: Missing.
**Severity**: REJECT

#### SEC-015 — Amicus: Disclosure Statement
**Rule**: 6.906(3)
**Pass if**: Disclosure statement about authorship and funding is present.
**Fail if**: Missing.
**Severity**: CORRECTION

#### CNT-001 — Party References Use Actual Names
**Rule**: 6.904(1) — counsel should use parties' actual names
**Pass if**: The brief primarily uses actual names or lower-court designations.
**Fail if**: The brief predominantly uses "Appellant"/"Appellee" instead of names.
**Severity**: CORRECTION

#### CNT-002 — Brief Is Concise, No Irrelevant Matter
**Rule**: 6.903 — brief must be concise
**Pass if**: The brief appears focused and relevant.
**Fail if**: Contains clearly irrelevant, scandalous, or grossly repetitive material.
**Severity**: NOTE

#### CNT-003 — Statutes/Rules in Brief or Addendum
**Rule**: 6.904(3) — relevant statutes/rules must be set out in the brief or addendum
**Pass if**: Relevant statutes/rules are quoted or an addendum contains them.
**Fail if**: Statutory language is argued about but not quoted.
**Severity**: NOTE

#### REC-002 — Record Citation Format
**Rule**: 6.904(2) — record citations should use (App. pp. ___) or (Tr. p. ___) format
**Pass if**: Record citations consistently use the appendix/transcript format.
**Fail if**: The brief uses non-standard formats for most record citations.
**Severity**: CORRECTION

#### REC-003 — Record Citations Identify Items
**Rule**: 6.904(2) — record references should include context identifying the item
**Pass if**: Record citations are generally accompanied by identifying context.
**Fail if**: Many citations are bare references with no surrounding context.
**Severity**: NOTE

## Recommendation Logic

1. **Hard-rule pass**: Any REJECT-severity failure → REJECT. Any CORRECTION-severity failure → CORRECTION_LETTER. Otherwise → ACCEPT.
2. In the skill workflow, recommendation is computed by `build_report.py` using hard-rule logic only (no API call).
