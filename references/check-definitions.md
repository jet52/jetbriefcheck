# Brief Compliance Check Definitions

All citations verified against the ND Rules of Appellate Procedure text.

## Mechanical Checks (Deterministic)

These are run by `check_brief.py` — no changes needed here.

| ID | Check | Rule | Failed Severity |
|---|---|---|---|
| FMT-001 | Paper size 8.5 x 11" | 32(a)(4) | REJECT |
| FMT-002 | Left margin >= 1.5" | 32(a)(4) | REJECT |
| FMT-003 | Right margin >= 1" | 32(a)(4) | CORRECTION |
| FMT-004 | Top margin >= 1" | 32(a)(4) | CORRECTION |
| FMT-005 | Bottom margin >= 1" | 32(a)(4) | CORRECTION | ⚠ High false-positive rate — page numbers often measured as content in margin zone |
| FMT-006 | Font size >= 12pt | 32(a)(5) | REJECT | ⚠ High false-positive rate — flags small fonts in page numbers, headers, superscripts |
| FMT-007 | Max 16 chars/inch | 32(a)(5) | CORRECTION |
| FMT-008 | Plain roman style | 32(a)(6) | NOTE |
| FMT-009 | Double-spaced body text | 32(a)(5) | CORRECTION | ⚠ High false-positive rate — spacing detection miscalibrated for many PDF encodings |
| FMT-010 | Footnotes double-spaced, same typeface | 32(a)(5) | NOTE |
| FMT-011 | Pages numbered at bottom | 32(a)(4) | CORRECTION |
| FMT-012 | Numbering starts with "1" on cover | 32(a)(4) | NOTE |
| PG-001 | Principal brief <= 38 pages (excl. addendum) | 32(a)(8) | REJECT |
| PG-002 | Reply brief <= 12 pages | 32(a)(8) | REJECT |
| PG-003 | Amicus brief <= 19 pages | 29(a)(5) | REJECT |
| PG-004 | Amicus rehearing <= 2,600 words | 29(b)(4) | REJECT |
| COV-001 | Cover color matches brief type | 32(a)(2) | CORRECTION |
| COV-002 | "ORAL ARGUMENT REQUESTED" on cover | 28(h)/34(a)(1)(C) | NOTE |
| CNT-004 | Paragraphs numbered (arabic numerals) | 32(a)(7) | CORRECTION |
| SEC-013 | Certificate of Compliance present | 32(d) | CORRECTION |
| REC-001 | Record citations present (R#:#) format | 30(a) | NOTE |

## Semantic Checks (Claude Code Evaluation)

These checks are evaluated by Claude Code during the skill workflow. For each check, read the brief's `full_text` and evaluate against the criteria below.

### Applicability by Brief Type

Before evaluating, filter checks by brief type:
- **All types**: SEC-001 through SEC-004, CNT-001, CNT-002, CNT-003, PRV-001
- **Appellant only**: SEC-005, SEC-006, SEC-007, SEC-008, SEC-010, SEC-011
- **Appellant + Appellee + Amicus**: SEC-009
- **Appellant + Appellee**: SEC-012
- **Appellant + Appellee + Cross-appeal**: REC-002, REC-003
- **Amicus only**: SEC-014, SEC-015

If a check is not applicable to the brief type, mark it as `"passed": true, "applicable": false` with message "Not applicable to {brief_type} briefs."

### Evaluation Guidance

For each applicable check, evaluate as follows. Cross-reference the rule text in `~/cDocs/refs/rules/ndrappp/` for exact rule language.

#### SEC-001 — Table of Contents Present
**Rule**: 28(b)(1) — "a table of contents, with paragraph references"
**Look for**: A section labeled "Table of Contents", "Contents", or similar near the beginning of the brief (typically after the cover page). The TOC should list the major sections/headings of the brief.
**Pass if**: A TOC section exists with section headings listed.
**Fail if**: No TOC is present at all.
**Severity**: REJECT

#### SEC-002 — TOC Uses Paragraph References
**Rule**: 28(b)(1) — requires "paragraph references"
**Look for**: Whether the TOC references use paragraph numbers (¶, ¶¶, [1], [2], etc.) as opposed to only page numbers. Under ND practice, briefs use paragraph numbering per Rule 32(a)(7), and the TOC should reference those paragraph numbers.
**Pass if**: TOC entries include paragraph references (¶ symbols or bracketed numbers pointing to paragraph numbers in the body).
**Fail if**: TOC entries use only page numbers with no paragraph references.
**Note**: Many briefs use page numbers in the TOC — this is a common deficiency. If the TOC uses page numbers exclusively, fail this check.
**Severity**: CORRECTION

#### SEC-003 — Table of Authorities Present
**Rule**: 28(b)(2) — "a table of authorities—cases (alphabetically arranged), statutes, and other authorities—with references to the paragraphs in the brief"
**Look for**: A section listing cases, statutes, and other authorities cited in the brief, typically after the TOC.
**Pass if**: A TOA section exists listing authorities.
**Fail if**: No TOA section is found.
**Severity**: REJECT

#### SEC-004 — TOA: Cases Alphabetical, Paragraph Refs
**Rule**: 28(b)(2)
**Look for**: (1) Cases listed in alphabetical order. (2) References use paragraph numbers rather than only page numbers.
**Pass if**: Cases appear alphabetical and references include paragraph numbers.
**Fail if**: Cases are not alphabetical, or references use only page numbers.
**Severity**: CORRECTION

#### SEC-005 — Jurisdictional Statement
**Rule**: 28(b)(3) — applies only to original jurisdiction applications
**Look for**: A statement of jurisdiction or basis for appellate jurisdiction. However, Rule 28(b)(3) specifically applies to "original proceedings" (original jurisdiction applications), not standard appeals.
**Pass if**: This is a standard appeal (not an original jurisdiction proceeding) — passes automatically. OR, if an original proceeding, a jurisdictional statement is present.
**Fail if**: This is an original jurisdiction proceeding and no jurisdictional statement is provided.
**Note**: Most appellate briefs are standard appeals, so this typically passes automatically. Only fail if the cover page or text clearly indicates an original proceeding (e.g., "Application for Supervisory Writ") AND no jurisdictional statement is found.
**Severity**: CORRECTION

#### SEC-006 — Statement of Issues
**Rule**: 28(b)(4) — "a statement of the issues presented for review"
**Look for**: A section titled "Statement of Issues", "Issues Presented", "Issues", or similar, listing the legal questions the court is asked to decide.
**Pass if**: An issues section exists with identifiable legal questions.
**Fail if**: No issues section is found.
**Severity**: REJECT

#### SEC-007 — Statement of the Case
**Rule**: 28(b)(5) — "a statement of the case briefly indicating the nature of the case, the course of the proceedings, and the disposition below"
**Look for**: A section describing the procedural history — the nature of the case, what happened in the lower court, and the disposition being appealed.
**Pass if**: A procedural history / statement of the case section exists.
**Fail if**: No such section is found. Note: sometimes combined with Statement of Facts — if procedural history is addressed there, it passes.
**Severity**: CORRECTION

#### SEC-008 — Statement of Facts with Record References
**Rule**: 28(b)(6) — "a statement of the facts relevant to the issues...with appropriate references to the record (see Rule 28(f))"
**Look for**: (1) A Statement of Facts section. (2) References to the record — look for citations like "App. 15", "Doc. 23", "(R. 45)", "Tr. 112", appendix references, or similar record citations.
**Pass if**: Facts section exists AND contains record references.
**Fail if**: No facts section, OR facts section lacks record references.
**Severity**: REJECT

#### SEC-009 — Argument Section Present
**Rule**: 28(b)(7) — "the argument"
**Look for**: A substantive section labeled "Argument" containing legal analysis with citations to authority.
**Pass if**: An argument section with legal analysis is present.
**Fail if**: No argument section found.
**Severity**: REJECT

#### SEC-010 — Standard of Review Stated
**Rule**: 28(b)(7)(B)(i) — "a concise statement of the applicable standard of review"
**Look for**: Either a standalone "Standard of Review" section or standard-of-review language within the argument (e.g., "de novo", "clearly erroneous", "abuse of discretion", "reasonable doubt").
**Pass if**: Standard of review is stated (either as a section or within the argument for each issue).
**Fail if**: No standard of review language found anywhere in the argument.
**Severity**: CORRECTION

#### SEC-011 — Preservation Citations
**Rule**: 28(b)(7)(B)(ii) — "citation to the record showing that the issue was preserved for review; or a statement of grounds for seeking review of an issue not preserved"
**Look for**: In the argument section, citations showing where each issue was raised below (e.g., "preserved at Tr. 45", "raised in motion at Doc. 12"), or a statement that the issue is raised for the first time on appeal with grounds for review (e.g., obvious error).
**Pass if**: The argument includes preservation citations or addresses preservation.
**Fail if**: No preservation language is found. However, be lenient — if the argument cites to the record in the course of arguing each issue, that may suffice.
**Severity**: NOTE

#### SEC-012 — Conclusion with Precise Relief
**Rule**: 28(b)(7)(D) — "a short conclusion stating the precise relief sought"
**Look for**: A "Conclusion" section that states what the party wants the court to do (e.g., "reverse and remand", "affirm the judgment", "reverse with instructions to dismiss").
**Pass if**: Conclusion exists and states specific relief sought.
**Fail if**: No conclusion, or conclusion is vague (e.g., "For the above reasons, the Court should rule in Appellant's favor" without specifying the relief).
**Severity**: CORRECTION

#### SEC-014 — Amicus: Identity/Interest Statement
**Rule**: 29(a)(4)(C) — "a concise statement of the identity of the amicus curiae, and its interest in the case"
**Look for**: A section identifying who the amicus is and why they have an interest in the case.
**Pass if**: Identity and interest statement is present.
**Fail if**: Missing.
**Severity**: REJECT

#### SEC-015 — Amicus: Disclosure Statement
**Rule**: 29(a)(4)(D) — disclosure of authorship and funding
**Look for**: A statement disclosing whether a party or party's counsel authored the brief and whether anyone other than the amicus or its counsel made a monetary contribution to the preparation or submission of the brief.
**Pass if**: Disclosure statement present.
**Fail if**: Missing.
**Severity**: CORRECTION

#### CNT-001 — Party References Use Actual Names
**Rule**: 28(e) — "counsel should use the parties' actual names or the designations used in the lower court"
**Look for**: Whether the brief predominantly uses actual party names (e.g., "Smith", "Kawasaki", "the City") versus procedural labels ("Appellant", "Appellee").
**Pass if**: The brief primarily uses actual names or lower-court designations. Occasional use of "Appellant"/"Appellee" for clarity is acceptable.
**Fail if**: The brief predominantly uses "Appellant"/"Appellee" instead of names.
**Note**: Rule 28(e) uses "should" — this is a preference, not an absolute command. Be somewhat lenient.
**Severity**: CORRECTION

#### CNT-002 — Brief Is Concise, No Irrelevant Matter
**Rule**: 28(l) — "must be concise...free from burdensome, irrelevant or immaterial matters"
**Look for**: Whether the brief contains obviously irrelevant, scandalous, or excessively repetitive material.
**Pass if**: The brief appears focused and relevant. Most briefs pass this check.
**Fail if**: The brief contains clearly irrelevant, scandalous, or grossly repetitive material.
**Note**: Apply a generous standard — only fail for egregious cases.
**Severity**: NOTE

#### CNT-003 — Statutes/Rules in Brief or Addendum
**Rule**: 28(g) — "the relevant parts must be set out in the brief or in an addendum"
**Look for**: If the brief discusses statutes, rules, or regulations, whether the relevant text is included in the brief body or in an addendum.
**Pass if**: Relevant statutes/rules are quoted or an addendum contains them, OR the brief does not involve statutory interpretation requiring the text.
**Fail if**: The brief argues about specific statutory/regulatory language that is neither quoted in the brief nor included in an addendum.
**Severity**: NOTE

#### PRV-001 — Privacy: Minor Names Redacted
**Rule**: N.D.R.Ct. 3.4(b)(1)(C) — "the name of an individual known to be a minor" must be redacted to "the minor's initials"
**Look for**: Whether the brief uses the full first or last name of any individual known to be a minor. Minors should be identified only by initials (e.g., "H.R.", "A.R.") throughout the brief. Check for inconsistent usage where initials are used in some places but full names appear elsewhere.
**Pass if**: All minors are consistently referred to by initials only. Using initials with periods (e.g., "H.R.") or without (e.g., "HR") is acceptable.
**Fail if**: A minor's full first name, last name, or both appear anywhere in the brief text (excluding the cover page party caption, where the parent's name naturally appears). Common indicators: the brief uses initials for a minor in most places but slips into using the actual name in others.
**Note**: Rule 3.4(b)(3)(E) exempts minors who are parties in certain case types (traffic, name change, conservatorship, protection orders). In a standard custody/family law appeal, the children are not parties and the exemption does not apply — initials are required. Be alert to first names appearing in quoted testimony or narrative that inadvertently reveal a minor's identity when initials are used elsewhere.
**Severity**: CORRECTION

#### REC-002 — Record Citation Format
**Rule**: 30(b)(1) — record citations must use the format (R{index}:{page}), e.g. (R156:12)
**Look for**: Whether record references consistently use the (R#:#) format. Note any citations that use other formats (e.g., "App. 15", "Doc. 23", "Tr. 45") instead.
**Pass if**: Record citations consistently use the (R#:#) format, or the brief uses a close variant (e.g., [R156:12]).
**Fail if**: The brief uses non-compliant formats for most record citations (e.g., "App." references, "Doc." references, or bare page numbers).
**Note**: If the brief uses a mix of formats, note which are non-compliant.
**Severity**: CORRECTION

#### REC-003 — Record Citations Identify Items
**Rule**: 30(a) — record references must include "information identifying the item, for example 'Statement of John Doe'"
**Look for**: Whether record citations provide enough context to identify what is being cited, either in the surrounding text or in the citation itself.
**Pass if**: Record citations are generally accompanied by identifying context (e.g., "Dr. Smith's deposition (R45:12)", "the district court's order (R102:1)").
**Fail if**: Many citations are bare references like (R12:5) with no surrounding context about what the item is.
**Note**: Be somewhat lenient — if the context is clear from the surrounding sentence, the citation need not repeat the identification.
**Severity**: NOTE

## Recommendation Logic

1. **Hard-rule pass**: Any REJECT-severity failure → REJECT. Any CORRECTION-severity failure → CORRECTION_LETTER. Otherwise → ACCEPT.
2. In the skill workflow, recommendation is computed by `build_report.py` using hard-rule logic only (no API call).
