---
name: jetbriefcheck
version: 2.1.0
description: >-
  Triggers when a user uploads a legal brief PDF for compliance review against the
  North Dakota Rules of Appellate Procedure. Analyzes the brief and produces a
  compliance report with a recommended action (Accept, Correction Letter, or Reject).
  Works with or without PyMuPDF — falls back to semantic-only checks when PyMuPDF
  is unavailable.
triggers:
  - brief compliance
  - check brief
  - compliance check
  - check appellate brief
  - appellate brief
  - legal brief review
  - brief PDF
  - ND rules compliance
---

# Appellate Brief Compliance Checker

## What This Skill Does

Analyzes an appellate brief PDF against the North Dakota Rules of Appellate Procedure and produces a detailed compliance report. The report includes:

- **Recommendation**: Accept, Correction Letter, or Reject
- **Mechanical checks** (when PyMuPDF is available): Paper size, margins, font size, spacing, page limits, page numbering, cover requirements
- **Semantic checks** (evaluated by Claude): Section presence and adequacy (TOC, TOA, Statement of Issues, Argument, etc.), party naming conventions, conciseness

This skill is self-contained. All rule text and check definitions are bundled below — no external file reads are required.

## Platform Detection

At the start of each CLI session, set variables for platform-dependent paths. **Do not use `$(uname)` or other command substitution** — it triggers unnecessary permission prompts. Instead, check for platform-specific files directly:

```bash
VENV_PYTHON=~/.claude/skills/jetbriefcheck/.venv/bin/python
if [ -f ~/.claude/skills/jetbriefcheck/.venv/Scripts/python.exe ]; then
  VENV_PYTHON=~/.claude/skills/jetbriefcheck/.venv/Scripts/python.exe
fi
```

If running in **PowerShell** (Windows without Git Bash):
```powershell
$VENV_PYTHON = "$HOME\.claude\skills\jetbriefcheck\.venv\Scripts\python.exe"
```

Use `$VENV_PYTHON` in all subsequent commands instead of hardcoded `python3`.

## Workflow

The user uploads a PDF via drag-and-drop. Save the uploaded file to a temporary location, then execute the phases below.

### Phase 0: Update Check and Save the Uploaded PDF

**Update check:** Run `python3 ~/.claude/skills/jetbriefcheck/check_update.py` silently. If it prints output, include it as a note to the user.

Save the uploaded file to the current working directory, preserving its original filename:

```python
import shutil, os
shutil.copy("<uploaded-file-path>", os.path.basename("<uploaded-file-path>"))
```

All intermediate and output files use the PDF stem in their names to avoid collisions (e.g., `Smith-v-Jones-Apt-Br-intermediate.json`, `Smith-v-Jones-Apt-Br-semantic.json`, `Smith-v-Jones-Apt-Br-compliance.html`).

### Phase 1: Try Mechanical Checks

Run the check script in mechanical-only mode. This makes **no API calls**:

```bash
$VENV_PYTHON scripts/check_brief.py "<filename>.pdf" --mechanical-only [--brief-type auto|appellant|appellee|reply|cross_appeal|amicus|petition_rehearing]
```

- **If the script succeeds**: Capture the intermediate JSON file path from stdout. Continue to **Phase 2 (Full Mode)**.
- **If the script fails** (e.g., `ModuleNotFoundError: No module named 'fitz'` or similar PyMuPDF error): Switch to **Phase 2F (Fallback Mode)**.

---

### Full Mode (PyMuPDF available)

#### Phase 2: Semantic Analysis (Claude)

You (Claude) perform the semantic analysis directly — no API call needed.

1. **Read the intermediate JSON** from Phase 1 to get `brief_type`, `full_text`, `cover_text`, and `mechanical_results`.

2. **Refer to the Bundled Rules section below** for the full text of all applicable rules.

3. **Refer to the Check Definitions section below** — the "Semantic Checks" subsection contains detailed evaluation guidance for each check ID.

4. **Evaluate each applicable semantic check** against the brief text, following the evaluation guidance in the Check Definitions. Filter by brief type first (see "Applicability by Brief Type" in Check Definitions).

5. **Write the semantic results** to `<pdf-stem>-semantic.json` in the current working directory. Use this exact schema:

```json
{
  "semantic_results": [
    {
      "check_id": "SEC-001",
      "name": "Table of Contents Present",
      "rule": "28(b)(1)",
      "passed": true,
      "severity": "reject",
      "message": "Table of Contents is present beginning on page 2.",
      "details": null,
      "applicable": true
    }
  ]
}
```

Each semantic check must appear in the results — either as an evaluated result (applicable: true) or as not-applicable (passed: true, applicable: false).

The severity values must be lowercase: `"reject"`, `"correction"`, or `"note"`.

#### Phase 3: Build Report (Script)

Run the report builder to merge results and generate the HTML report:

```bash
$VENV_PYTHON scripts/build_report.py \
  --intermediate "<intermediate-json-path>" \
  --semantic "<semantic-json-path>"
```

The script will:
1. Load mechanical results from the intermediate JSON
2. Load semantic results from the semantic JSON
3. Merge into a single results list
4. Compute a recommendation using hard-rule logic (no API call)
5. Generate an HTML report named `<brief-stem>-compliance.html` in the same directory as the original PDF
6. Print a JSON summary to stdout

#### Phase 4: Report to User

After Phase 3, report the findings to the user:
- State the **recommendation** (Accept, Correction Letter, or Reject)
- Summarize any **failed checks** grouped by severity
- Provide the generated HTML report as a downloadable file

---

### Fallback Mode (no PyMuPDF)

When PyMuPDF is not available, Claude performs semantic-only analysis by reading the PDF directly.

#### Phase 2F: Classify Brief Type

Read the uploaded PDF directly. Examine the cover page to determine the brief type:
- **Petition for Rehearing**: Cover says "Petition for Rehearing" or similar
- **Appellant**: Cover says "Brief of Appellant" or similar
- **Appellee**: Cover says "Brief of Appellee" or similar
- **Reply**: Cover says "Reply Brief" or similar
- **Cross-appeal**: Cover references cross-appeal
- **Amicus**: Cover says "Brief of Amicus Curiae" or similar

If unclear, ask the user.

#### Phase 3F: Evaluate Semantic Checks

Using the full text of the PDF (which Claude can read directly):

1. **Refer to the Bundled Rules section below** for the full text of all applicable rules.
2. **Refer to the Check Definitions section below** for semantic check evaluation guidance.
3. **Evaluate each applicable semantic check** against the brief text, filtering by brief type first (see "Applicability by Brief Type").
4. For each check, record: check ID, name, rule, passed/failed, severity, and a message explaining the finding.

#### Phase 4F: Report to User

Produce a structured text report with:

1. **Header**: Brief filename, brief type, date of analysis
2. **Recommendation**: Apply the recommendation logic (any REJECT-severity failure → Reject; any CORRECTION-severity failure → Correction Letter; otherwise → Accept)
3. **Note**: "Mechanical checks (margins, font size, spacing, page limits, paper size) were skipped because PyMuPDF is not available. Only semantic checks were performed."
4. **Findings**: Group results by severity (REJECT, CORRECTION, NOTE), listing failed checks first, then passed checks
5. For each failed check: check ID, name, rule reference, severity, and explanation

---

## Output

- **Full mode**: An HTML compliance report file + JSON summary
- **Fallback mode**: A structured text compliance report (semantic checks only)

## Requirements

- **Full mode**: Python with PyMuPDF installed (`pip install PyMuPDF`)
- **Fallback mode**: No dependencies — Claude reads the PDF and evaluates checks directly
- No API keys needed — semantic analysis is performed by Claude directly

## Known Issues

Based on testing across 13 briefs (Feb 2026):

### Mechanical Check False Positives

Two mechanical checks have high false-positive rates. When reporting results, note these caveats to the user:

- **FMT-006 (Font Size)**: Measures the minimum font found anywhere in the PDF. Small fonts in page numbers, headers, footers, superscripts, or PDF artifacts trigger REJECT even when the body text is properly 12pt. If this is the sole REJECT trigger and the reported minimum is 8-11pt, flag it as a likely false positive.
- **FMT-005 (Bottom Margin)**: Page numbers at the bottom are measured as content in the margin zone. Nearly always triggers.

**Fixed (v1.6.0):** FMT-009 (Spacing) previously only measured intra-block line gaps, missing PDFs that encode each line as a separate text block. Now also measures inter-block baseline distances, which correctly detects double spacing in these PDFs.

### Brief Type Auto-Detection

The `--brief-type auto` flag frequently returns "unknown", especially for appellee briefs. If auto-detection fails, re-run Phase 1 with an explicit `--brief-type` flag based on the cover page text.

### Detection Variants

- **COV-002 (Oral Argument)**: Misses "REQUEST FOR ORAL ARGUMENT" — only matches "ORAL ARGUMENT REQUESTED".
- **SEC-013 (Certificate of Compliance)**: Misses "CERTIFICATION OF COMPLIANCE" variant.

### Non-Appellate Briefs

The test corpus may include non-appellate briefs (e.g., "Brief in Support of Motion"). These are not subject to Rules 28/32 and should be skipped. Check the cover page and brief content before proceeding.

### Fallback Mode Limitations

When running in fallback mode (no PyMuPDF), mechanical checks are entirely skipped. The report will not include results for paper size, margins, font size, spacing, page limits, page numbering, or cover color. Only semantic checks are evaluated.

## References

- [Rules Summary](references/rules-summary.md) — Condensed ND Rules of Appellate Procedure
- [Check Definitions](references/check-definitions.md) — Full catalog of checks (also bundled below)
- [Bundled Rules](references/rules/) — Full rule text files (also bundled below)

---

## Check Definitions

All citations verified against the ND Rules of Appellate Procedure text.

### Mechanical Checks (Deterministic)

These are run by `check_brief.py` — no changes needed here.

| ID | Check | Rule | Failed Severity |
|---|---|---|---|
| FMT-001 | Paper size 8.5 x 11" | 32(a)(4) | REJECT |
| FMT-002 | Left margin >= 1.5" | 32(a)(4) | REJECT |
| FMT-003 | Right margin >= 1" | 32(a)(4) | CORRECTION |
| FMT-004 | Top margin >= 1" | 32(a)(4) | CORRECTION |
| FMT-005 | Bottom margin >= 1" (excluding page numbers) | 32(a)(4) | CORRECTION |
| FMT-006 | Font size >= 12pt | 32(a)(5) | REJECT | ⚠ High false-positive rate — flags small fonts in page numbers, headers, superscripts |
| FMT-007 | Max 16 chars/inch | 32(a)(5) | CORRECTION |
| FMT-008 | Plain roman style | 32(a)(6) | NOTE |
| FMT-009 | Double-spaced body text | 32(a)(5) | CORRECTION |
| FMT-010 | Footnotes double-spaced, same typeface | 32(a)(5) | NOTE |
| FMT-011 | Pages numbered at bottom | 32(a)(4) | CORRECTION |
| FMT-012 | Numbering starts with "1" on cover | 32(a)(4) | NOTE |
| PG-001 | Principal brief <= 38 pages (excl. addendum) | 32(a)(8) | REJECT |
| PG-002 | Reply brief <= 12 pages | 32(a)(8) | REJECT |
| PG-003 | Amicus brief <= 19 pages | 29(a)(5) | REJECT |
| PG-004 | Amicus rehearing <= 2,600 words | 29(b)(4) | REJECT |
| PG-005 | Petition for rehearing <= 10 pages (excl. addendum) | 40(b) | REJECT |
| COV-001 | Cover color matches brief type | 32(a)(2) | CORRECTION |
| COV-002 | "ORAL ARGUMENT REQUESTED" on cover | 28(h)/34(a)(1)(C) | NOTE |
| CNT-004 | Paragraphs numbered (arabic numerals) | 32(a)(7) | CORRECTION |
| SEC-013 | Certificate of Compliance present | 32(d) | CORRECTION |
| REC-001 | Record citations present (R#:#) format | 30(a) | NOTE |
| CIT-001 | ND case citations: medium-neutral format | N.D.R.Ct. 11.6(b) | CORRECTION |

### Semantic Checks (Claude Evaluation)

These checks are evaluated by Claude during the skill workflow. For each check, read the brief's `full_text` and evaluate against the criteria below.

#### Applicability by Brief Type

Before evaluating, filter checks by brief type:
- **All types**: SEC-001 through SEC-004, CNT-001, CNT-002, CNT-003, PRV-001, PRV-002 through PRV-006, WRT-001 through WRT-003, CIT-002
- **Appellant only**: SEC-005, SEC-006, SEC-007, SEC-008, SEC-010, SEC-011
- **Appellant + Appellee + Amicus**: SEC-009
- **Appellant + Appellee**: SEC-012
- **Appellant + Appellee + Cross-appeal**: REC-002, REC-003
- **Amicus only**: SEC-014, SEC-015
- **Petition for Rehearing only**: RHR-001, RHR-002, RHR-003

Note: PRV-002–006, WRT-001–003, and CIT-002 are applicable to all brief types but auto-pass when the case type or document type doesn't trigger them (e.g., WRT checks auto-pass if the document is not a writ petition).

If a check is not applicable to the brief type, mark it as `"passed": true, "applicable": false` with message "Not applicable to {brief_type} briefs."

#### Evaluation Guidance

For each applicable check, evaluate as follows. Cross-reference the rule text in the Bundled Rules section below for exact rule language.

##### SEC-001 — Table of Contents Present
**Rule**: 28(b)(1) — "a table of contents, with paragraph references"
**Look for**: A section labeled "Table of Contents", "Contents", or similar near the beginning of the brief (typically after the cover page). The TOC should list the major sections/headings of the brief.
**Pass if**: A TOC section exists with section headings listed.
**Fail if**: No TOC is present at all.
**Severity**: REJECT

##### SEC-002 — TOC Uses Paragraph References
**Rule**: 28(b)(1) — requires "paragraph references"
**Look for**: Whether the TOC references use paragraph numbers (¶, ¶¶, [1], [2], etc.) as opposed to only page numbers. Under ND practice, briefs use paragraph numbering per Rule 32(a)(7), and the TOC should reference those paragraph numbers.
**Pass if**: TOC entries include paragraph references (¶ symbols or bracketed numbers pointing to paragraph numbers in the body).
**Fail if**: TOC entries use only page numbers with no paragraph references.
**Note**: Many briefs use page numbers in the TOC — this is a common deficiency. If the TOC uses page numbers exclusively, fail this check.
**Severity**: CORRECTION

##### SEC-003 — Table of Authorities Present
**Rule**: 28(b)(2) — "a table of authorities—cases (alphabetically arranged), statutes, and other authorities—with references to the paragraphs in the brief"
**Look for**: A section listing cases, statutes, and other authorities cited in the brief, typically after the TOC.
**Pass if**: A TOA section exists listing authorities.
**Fail if**: No TOA section is found.
**Severity**: REJECT

##### SEC-004 — TOA: Cases Alphabetical, Paragraph Refs
**Rule**: 28(b)(2)
**Look for**: (1) Cases listed in alphabetical order. (2) References use paragraph numbers rather than only page numbers.
**Pass if**: Cases appear alphabetical and references include paragraph numbers.
**Fail if**: Cases are not alphabetical, or references use only page numbers.
**Severity**: CORRECTION

##### SEC-005 — Jurisdictional Statement
**Rule**: 28(b)(3) — applies only to original jurisdiction applications
**Look for**: A statement of jurisdiction or basis for appellate jurisdiction. However, Rule 28(b)(3) specifically applies to "original proceedings" (original jurisdiction applications), not standard appeals.
**Pass if**: This is a standard appeal (not an original jurisdiction proceeding) — passes automatically. OR, if an original proceeding, a jurisdictional statement is present.
**Fail if**: This is an original jurisdiction proceeding and no jurisdictional statement is provided.
**Note**: Most appellate briefs are standard appeals, so this typically passes automatically. Only fail if the cover page or text clearly indicates an original proceeding (e.g., "Application for Supervisory Writ") AND no jurisdictional statement is found.
**Severity**: CORRECTION

##### SEC-006 — Statement of Issues
**Rule**: 28(b)(4) — "a statement of the issues presented for review"
**Look for**: A section titled "Statement of Issues", "Issues Presented", "Issues", or similar, listing the legal questions the court is asked to decide.
**Pass if**: An issues section exists with identifiable legal questions.
**Fail if**: No issues section is found.
**Severity**: REJECT

##### SEC-007 — Statement of the Case
**Rule**: 28(b)(5) — "a statement of the case briefly indicating the nature of the case, the course of the proceedings, and the disposition below"
**Look for**: A section describing the procedural history — the nature of the case, what happened in the lower court, and the disposition being appealed.
**Pass if**: A procedural history / statement of the case section exists.
**Fail if**: No such section is found. Note: sometimes combined with Statement of Facts — if procedural history is addressed there, it passes.
**Severity**: CORRECTION

##### SEC-008 — Statement of Facts with Record References
**Rule**: 28(b)(6) — "a statement of the facts relevant to the issues...with appropriate references to the record (see Rule 28(f))"
**Look for**: (1) A Statement of Facts section. (2) References to the record — look for citations like "App. 15", "Doc. 23", "(R. 45)", "Tr. 112", appendix references, or similar record citations.
**Pass if**: Facts section exists AND contains record references.
**Fail if**: No facts section, OR facts section lacks record references.
**Severity**: REJECT

##### SEC-009 — Argument Section Present
**Rule**: 28(b)(7) — "the argument"
**Look for**: A substantive section labeled "Argument" containing legal analysis with citations to authority.
**Pass if**: An argument section with legal analysis is present.
**Fail if**: No argument section found.
**Severity**: REJECT

##### SEC-010 — Standard of Review Stated
**Rule**: 28(b)(7)(B)(i) — "a concise statement of the applicable standard of review"
**Look for**: Either a standalone "Standard of Review" section or standard-of-review language within the argument (e.g., "de novo", "clearly erroneous", "abuse of discretion", "reasonable doubt").
**Pass if**: Standard of review is stated (either as a section or within the argument for each issue).
**Fail if**: No standard of review language found anywhere in the argument.
**Severity**: CORRECTION

##### SEC-011 — Preservation Citations
**Rule**: 28(b)(7)(B)(ii) — "citation to the record showing that the issue was preserved for review; or a statement of grounds for seeking review of an issue not preserved"
**Look for**: In the argument section, citations showing where each issue was raised below (e.g., "preserved at Tr. 45", "raised in motion at Doc. 12"), or a statement that the issue is raised for the first time on appeal with grounds for review (e.g., obvious error).
**Pass if**: The argument includes preservation citations or addresses preservation.
**Fail if**: No preservation language is found. However, be lenient — if the argument cites to the record in the course of arguing each issue, that may suffice.
**Severity**: NOTE

##### SEC-012 — Conclusion with Precise Relief
**Rule**: 28(b)(7)(D) — "a short conclusion stating the precise relief sought"
**Look for**: A "Conclusion" section that states what the party wants the court to do (e.g., "reverse and remand", "affirm the judgment", "reverse with instructions to dismiss").
**Pass if**: Conclusion exists and states specific relief sought.
**Fail if**: No conclusion, or conclusion is vague (e.g., "For the above reasons, the Court should rule in Appellant's favor" without specifying the relief).
**Severity**: CORRECTION

##### SEC-014 — Amicus: Identity/Interest Statement
**Rule**: 29(a)(4)(C) — "a concise statement of the identity of the amicus curiae, and its interest in the case"
**Look for**: A section identifying who the amicus is and why they have an interest in the case.
**Pass if**: Identity and interest statement is present.
**Fail if**: Missing.
**Severity**: REJECT

##### SEC-015 — Amicus: Disclosure Statement
**Rule**: 29(a)(4)(D) — disclosure of authorship and funding
**Look for**: A statement disclosing whether a party or party's counsel authored the brief and whether anyone other than the amicus or its counsel made a monetary contribution to the preparation or submission of the brief.
**Pass if**: Disclosure statement present.
**Fail if**: Missing.
**Severity**: CORRECTION

##### CNT-001 — Party References Use Actual Names
**Rule**: 28(e) — "counsel should use the parties' actual names or the designations used in the lower court"
**Look for**: Whether the brief predominantly uses actual party names (e.g., "Smith", "Kawasaki", "the City") versus procedural labels ("Appellant", "Appellee").
**Pass if**: The brief primarily uses actual names or lower-court designations. Occasional use of "Appellant"/"Appellee" for clarity is acceptable.
**Fail if**: The brief predominantly uses "Appellant"/"Appellee" instead of names.
**Note**: Rule 28(e) uses "should" — this is a preference, not an absolute command. Be somewhat lenient.
**Severity**: CORRECTION

##### CNT-002 — Brief Is Concise, No Irrelevant Matter
**Rule**: 28(l) — "must be concise...free from burdensome, irrelevant or immaterial matters"
**Look for**: Whether the brief contains obviously irrelevant, scandalous, or excessively repetitive material.
**Pass if**: The brief appears focused and relevant. Most briefs pass this check.
**Fail if**: The brief contains clearly irrelevant, scandalous, or grossly repetitive material.
**Note**: Apply a generous standard — only fail for egregious cases.
**Severity**: NOTE

##### CNT-003 — Statutes/Rules in Brief or Addendum
**Rule**: 28(g) — "the relevant parts must be set out in the brief or in an addendum"
**Look for**: If the brief discusses statutes, rules, or regulations, whether the relevant text is included in the brief body or in an addendum.
**Pass if**: Relevant statutes/rules are quoted or an addendum contains them, OR the brief does not involve statutory interpretation requiring the text.
**Fail if**: The brief argues about specific statutory/regulatory language that is neither quoted in the brief nor included in an addendum.
**Severity**: NOTE

##### PRV-001 — Privacy: Minor Names Redacted
**Rule**: N.D.R.Ct. 3.4(b)(1)(C) — "the name of an individual known to be a minor" must be redacted to "the minor's initials"
**Cross-reference**: Rule 14(a)(5) also requires minor children to be referred to by initials. PRV-001 covers this obligation under both rules.
**Look for**: Whether the brief uses the full first or last name of any individual known to be a minor. Minors should be identified only by initials (e.g., "H.R.", "A.R.") throughout the brief. Check for inconsistent usage where initials are used in some places but full names appear elsewhere.
**Pass if**: All minors are consistently referred to by initials only. Using initials with periods (e.g., "H.R.") or without (e.g., "HR") is acceptable.
**Fail if**: A minor's full first name, last name, or both appear anywhere in the brief text (excluding the cover page party caption, where the parent's name naturally appears). Common indicators: the brief uses initials for a minor in most places but slips into using the actual name in others.
**Note**: Rule 3.4(b)(3)(E) exempts minors who are parties in certain case types (traffic, name change, conservatorship, protection orders). In a standard custody/family law appeal, the children are not parties and the exemption does not apply — initials are required. Be alert to first names appearing in quoted testimony or narrative that inadvertently reveal a minor's identity when initials are used elsewhere.
**Severity**: CORRECTION

##### REC-002 — Record Citation Format
**Rule**: 30(b)(1) — record citations must use the format (R{index}:{page}), e.g. (R156:12)
**Look for**: Whether record references consistently use the (R#:#) format. Note any citations that use other formats (e.g., "App. 15", "Doc. 23", "Tr. 45") instead.
**Pass if**: Record citations consistently use the (R#:#) format, or the brief uses a close variant (e.g., [R156:12]).
**Fail if**: The brief uses non-compliant formats for most record citations (e.g., "App." references, "Doc." references, or bare page numbers).
**Note**: If the brief uses a mix of formats, note which are non-compliant.
**Severity**: CORRECTION

##### REC-003 — Record Citations Identify Items
**Rule**: 30(a) — record references must include "information identifying the item, for example 'Statement of John Doe'"
**Look for**: Whether record citations provide enough context to identify what is being cited, either in the surrounding text or in the citation itself.
**Pass if**: Record citations are generally accompanied by identifying context (e.g., "Dr. Smith's deposition (R45:12)", "the district court's order (R102:1)").
**Fail if**: Many citations are bare references like (R12:5) with no surrounding context about what the item is.
**Note**: Be somewhat lenient — if the context is clear from the surrounding sentence, the citation need not repeat the identification.
**Severity**: NOTE

##### PRV-002 — Identity Protection: Mental Health Respondent
**Rule**: 14(a)(1) — respondent in a mental health proceeding must be referred to by initials only
**Look for**: First determine if this is a mental health case (indicators: "mental health commitment", "treatment order", N.D.C.C. ch. 25-03.1). If not, pass automatically. If it is, check whether the respondent's full name appears anywhere — it should be initials only.
**Pass if**: Not a mental health case, OR respondent consistently uses initials.
**Fail if**: Mental health case and respondent's full name appears.
**Severity**: CORRECTION

##### PRV-003 — Identity Protection: Guardianship/Conservatorship
**Rule**: 14(a)(2) — respondent and family members in guardianship/conservatorship must use initials
**Look for**: Determine if this is a guardianship or conservatorship case. If not, pass automatically. If it is, check that the respondent and family members use initials only.
**Pass if**: Not a guardianship/conservatorship case, OR all protected individuals use initials.
**Fail if**: Guardianship/conservatorship case and protected individuals' names appear.
**Severity**: CORRECTION

##### PRV-004 — Identity Protection: Juvenile Respondent
**Rule**: 14(a)(3) — respondent in a juvenile proceeding must use initials
**Look for**: Determine if this is a juvenile case (indicators: "juvenile", "delinquent", N.D.C.C. ch. 27-20). If not, pass automatically. If it is, check that the juvenile respondent uses initials.
**Pass if**: Not a juvenile case, OR juvenile respondent consistently uses initials.
**Fail if**: Juvenile case and respondent's full name appears.
**Severity**: CORRECTION

##### PRV-005 — Identity Protection: TPR Proceedings
**Rule**: 14(a)(4) — child and family members in TPR proceedings must use initials
**Look for**: Determine if this is a termination of parental rights case ("TPR", "termination of parental rights"). If not, pass automatically. If it is, check that the child and family members use initials.
**Pass if**: Not a TPR case, OR all protected individuals use initials.
**Fail if**: TPR case and protected individuals' full names appear.
**Severity**: CORRECTION

##### PRV-006 — Identity Protection: Sexual Offense Victim
**Rule**: 14(a)(6) — victim or alleged victim of a sexual offense must use initials
**Look for**: Determine if the case involves a sexual offense (sexual assault, rape, gross sexual imposition, N.D.C.C. ch. 12.1-20). If not, pass automatically. If it is, check that the victim is referred to by initials only.
**Pass if**: Not a sexual offense case, OR victim consistently uses initials.
**Fail if**: Sexual offense case and victim's full name appears.
**Severity**: CORRECTION

##### WRT-001 — Writ Petition: Required Content
**Rule**: 21(a)(2) — petition must state relief sought, issues, facts, and reasons
**Look for**: First determine if this is a writ petition (indicators: "supervisory writ", "writ of mandamus", "writ of prohibition", "extraordinary writ"). If not, pass automatically. If it is, check that the petition states (A) relief sought, (B) issues presented, (C) necessary facts, and (D) reasons why a writ should issue.
**Pass if**: Not a writ petition, OR all four elements are present.
**Fail if**: Writ petition missing one or more required elements.
**Severity**: CORRECTION

##### WRT-002 — Writ Petition: Supporting Documents
**Rule**: 21(a)(3) — petition must include supporting documents
**Look for**: If not a writ petition, pass automatically. If it is, check whether supporting documents (orders, record excerpts) are referenced or attached as exhibits.
**Pass if**: Not a writ petition, OR supporting documents are included.
**Fail if**: Writ petition with no supporting documents referenced.
**Severity**: CORRECTION

##### WRT-003 — Writ Petition: Exhibit Citation Format
**Rule**: 21(a)(3)(B) — supporting documents should use (E{page}:{line/para}) format
**Look for**: If not a writ petition, pass automatically. If it is, check whether exhibit citations use the (E#:#) format, e.g. (E6:12:¶3).
**Pass if**: Not a writ petition, OR exhibit citations use proper format.
**Fail if**: Writ petition with exhibit citations not using (E#:#) format.
**Note**: This is advisory — the format is recommended, not strictly required.
**Severity**: NOTE

##### RHR-001 — Rehearing: Points Overlooked or Misapprehended
**Rule**: 40(a)(2) — "state with particularity each point of law or fact that the petitioner believes the court has overlooked or misapprehended"
**Look for**: Specific identification of points of law or fact the petitioner claims the court overlooked or misunderstood. The petition should not merely reargue the case.
**Pass if**: Not a petition for rehearing, OR the petition identifies specific points with particularity.
**Fail if**: Petition for rehearing that fails to identify specific points the court allegedly overlooked or misapprehended, or merely reargues the merits without identifying particular errors.
**Severity**: REJECT

##### RHR-002 — Rehearing: Applicable Rule 28(b) Items
**Rule**: 40(b) — "must include items required under Rule 28(b) that are applicable"
**Look for**: Whether the petition includes applicable Rule 28(b) items, particularly a table of contents (28(b)(1)) and table of authorities (28(b)(2)). For short petitions (under ~5 pages), the absence of a TOC/TOA may be reasonable.
**Pass if**: Not a petition for rehearing, OR the petition includes applicable Rule 28(b) items (or is short enough that their absence is reasonable).
**Fail if**: Petition for rehearing of substantial length that omits a TOC or TOA.
**Severity**: CORRECTION

##### RHR-003 — Rehearing: Supporting Argument
**Rule**: 40(a)(2) — "must contain such argument in support of the petition as the petitioner desires to present"
**Look for**: Substantive argument supporting the claim that the court overlooked or misapprehended specific points.
**Pass if**: Not a petition for rehearing, OR the petition contains a substantive argument section.
**Fail if**: Petition for rehearing with no meaningful argument supporting the identified points.
**Severity**: REJECT

##### CIT-002 — ND Case Citations: Pre/Post-1997 Compliance
**Rule**: N.D.R.Ct. 11.6 — medium-neutral citations required for post-1997 ND opinions
**Look for**: Whether the brief correctly applies the pre-1997 vs post-1997 distinction. Post-1997 opinions must include "YYYY ND ##" format. Pre-1997 opinions need only the N.W.2d citation.
**Pass if**: Citations correctly distinguish pre- and post-1997 cases.
**Fail if**: Post-1997 cases cited without medium-neutral format, or other misapplication of the rule.
**Note**: Be lenient — this is an advisory check. CIT-001 (mechanical) catches the most obvious violations.
**Severity**: NOTE

### Recommendation Logic

1. **Hard-rule pass**: Any REJECT-severity failure → REJECT. Any CORRECTION-severity failure → CORRECTION_LETTER. Otherwise → ACCEPT.
2. In the skill workflow, recommendation is computed by `build_report.py` using hard-rule logic only (no API call). In fallback mode, Claude applies this same logic directly.

---

## Bundled Rules

### N.D.R.App.P. 28 — Briefs

**(a) Form of Briefs.** All briefs must comply with Rule 25 and Rule 32.

**(b) Appellant's Brief.** The appellant's brief must contain, under appropriate headings and in the order indicated:

> (1) a table of contents, with paragraph references;

> (2) a table of authorities—cases (alphabetically arranged), statutes, and other authorities—with references to the paragraphs in the brief where they are cited;

> (3) in an application for the exercise of original jurisdiction, a concise statement of the grounds on which the jurisdiction of the supreme court is invoked, including citations of authorities;

> (4) a statement of the issues presented for review;

> (5) a statement of the case briefly indicating the nature of the case, the course of the proceedings, and the disposition below;

> (6) a statement of the facts relevant to the issues submitted for review, which identifies facts in dispute and includes appropriate references to the record (see Rule 28(f));

> (7) the argument, which must contain:

> > (A) appellant's contentions and the reasons for them, with citations to the authorities and parts of the record on which the appellant relies; and

> > (B) for each issue:

> > > (i) a concise statement of the applicable standard of review (which may appear in the discussion of the issue or under a separate heading placed before the discussion of the issues);

> > > (ii) citation to the record showing that the issue was preserved for review; or a statement of grounds for seeking review of an issue not preserved; and

> > (C) if the appeal is from a judgment ordered under N.D.R.Civ.P. 54(b), whether the certification was appropriate; and

> > (D) a short conclusion stating the precise relief sought.

**(c) Appellee's Brief.** The appellee's brief must conform to the requirements of subdivision (b), except that none of the following need appear unless the appellee is dissatisfied with the appellant's statement:

> (1) the jurisdictional statement;

> (2) the statement of the issues;

> (3) the statement of the case;

> (4) the statement of the facts; and

> (5) the statement of the standard of review.

**(d) Reply Brief.** The appellant may file a single brief in reply to the appellee's brief. Unless the court permits, no further briefs may be filed. A reply brief must contain a table of contents, with paragraph references, and a table of authorities—cases (alphabetically arranged), statutes, and other authorities—with references to the paragraphs in the reply brief where they are cited.

**(e) References to Parties.** Except as required under Rule 14, counsel should use the parties' actual names or the designations used in the lower court or agency proceeding, or such descriptive terms as "the employee," "the injured person," "the taxpayer," "the purchaser."

**(f) References to the Record.** References to the record must be made as provided by Rule 30.

**(g) Reproduction of Statutes, Rules, Regulations, and Other Sources.** If the court's determination of the issues presented requires the study of statutes, rules, regulations, etc., the relevant parts must be set out in the brief or in an addendum at the end of the brief.

**(h) Oral Arguments Requested.** Any party who desires oral argument must place the words "ORAL ARGUMENT REQUESTED" conspicuously on the cover page of the appellant's, appellee's or cross-appellee's reply brief.

**(i) Briefs in a Case Involving a Cross-Appeal.**

> (1) An appellee and cross-appellant must file a single brief at the time the appellee's brief is due. This brief must contain the issues and argument involved in the cross-appeal as well as the answer to the appellant's brief.

> (2) The appellant's answer to the cross-appeal must be included in the reply brief, but without duplication of statements, arguments, or authorities contained in the appellant's principal brief. To avoid duplication, references may be made to the appropriate portions of the appellant's principal brief.

> (3) The cross-appellant may file a reply brief confined strictly to the arguments raised in the cross-appeal. This brief is due within 14 days after service of the appellant's reply brief; however, if there is less than 14 days before oral argument, the reply brief must be filed at least 5 days before argument.

**(j) Briefs In a Case Involving Multiple Parties.** Any number of parties may join in a single brief or adopt by reference any part of another's brief. Parties may similarly join in reply briefs.

**(k) Citation of Supplemental Authorities.** If pertinent and significant authorities come to a party's attention after the party's brief has been filed—or after oral argument but before decision—a party may promptly advise the court by letter, with a copy to all other parties, setting forth the citations. The letter must state without argument the reasons for the supplemental citations, referring either to the page of the brief or to a point argued orally. Any response must be made promptly and must be similarly limited.

**(l) Requirements.** All briefs under this rule must be concise, presented with accuracy, logically arranged with proper headings, and free from burdensome, irrelevant or immaterial matters.

### N.D.R.App.P. 29 — Brief of an Amicus Curiae

**(a) During Initial Consideration of a Case on the Merits.**

> (1) Applicability. This Rule 29(a) governs amicus filings during a court's initial consideration of a case on the merits.

> (2) When Permitted. An amicus curiae brief may be filed only with leave of court or at the court's request. An amicus brief must be limited to issues raised on appeal by the parties.

> (3) Motion for Leave to File. The motion may be accompanied by the proposed brief. The motion must state:

> > (A) the moving party's interest; and

> > (B) the reasons why an amicus brief is desirable and why the matters asserted are relevant to the disposition of the case.

> (4) Contents and Form. An amicus brief must comply with Rule 25 and Rule 32. In addition to the requirements of Rule 25 and Rule 32, the cover must identify the party or parties supported, if any, and indicate whether the brief supports affirmance or reversal. An amicus brief need not comply with Rule 28, but must include the following:

> > (A) a table of contents, with paragraph references;

> > (B) a table of authorities—cases (alphabetically arranged), statutes and other authorities—with references to the paragraphs in the brief where they are cited;

> > (C) a concise statement of the identity of the amicus curiae, and its interest in the case;

> > (D) a statement that indicates whether:

> > > (i) a party's counsel authored the brief in whole or in part;

> > > (ii) a party or a party's counsel contributed money that was intended to fund preparing or submitting the brief; and

> > > (iii) a person—other than the amicus curiae, its members, or its counsel—contributed money that was intended to fund preparing or submitting the brief and, if so, identifies each such person; and

> > > (iv) an argument, which may be preceded by a summary and which need not include a statement of the applicable standard of review.

> (5) Length. Except by the court's permission, an amicus brief may be no more than one-half the maximum length authorized by these rules for a party's principal brief (see Rule 32(a)(8)). If the court grants a party permission to file a longer brief, that extension does not affect the length of an amicus brief.

> (6) Time for Filing. An amicus curiae must file its brief within the time allowed for filing the principal brief of the party being supported. An amicus curiae that does not support either party must file its brief within the time allowed for filing the appellant's principal brief. The court may grant leave for later filing, specifying the time within which an opposing party may answer.

> (7) Reply Brief. Except by the court's permission, an amicus curiae may not file a reply brief.

> (8) Oral Argument. An amicus curiae may participate in oral argument only with the court's permission.

**(b) During Consideration of Whether to Grant Rehearing.**

> (1) Applicability. This Rule 29(b) governs amicus filings during a court's consideration of whether to grant rehearing.

> (2) When Permitted. An amicus curiae may file a brief only by leave of court.

> (3) Motion for Leave to File. Rule 29(a)(3) applies to a motion for leave.

> (4) Contents, Form, and Length. Rule 29(a)(4) applies to the amicus brief. The brief must not exceed 2,600 words.

> (5) Time for Filing. An amicus curiae supporting the petition for rehearing or supporting neither party must file its brief, accompanied by a motion for filing when necessary, no later than 7 days after the petition is filed. An amicus curiae opposing the petition must file its brief, accompanied by a motion for filing when necessary, no later than the date set by the court for the response.

### N.D.R.App.P. 30 — References to the Record

**(a) In General.** In any document submitted to the supreme court, references to evidence or other parts of the record must include a citation to a register of actions index number or to the location in the recording where such evidence or other material appears. The reference must include, either in the document text or the citation itself, information identifying the item, for example "Statement of John Doe."

**(b) Form of Citation.**

> **(1)** Reference to any material that is contained in an item in the record and that is listed under a register of actions index number, including transcripts, must be made by setting forth in parentheses the capital letter "R" followed by the index number of the item followed by a colon and the specific page within the item where the information referred to is located, for example (R156:12). If applicable, paragraph or line numbers must be included after the page number, for example (R156:12:¶3) or (R156:12:3). Where more than one district court record must be cited, on first reference to the matter include the entire district court case number (54-2020-CV-00012 R19:2), and on subsequent references include only the last four digits (0012 R19:2).

> **(2)** References to a video or audio recording in the record must be made by identifying the recording and providing specific, time-coded locations of the relevant portions.

### N.D.R.App.P. 32 — Form of Briefs and Other Documents

**(a) Form of a Brief.**

> **(1) Reproduction.**

> > (A) A brief must be typewritten, printed, or reproduced by any process that yields a clear black image on white paper. Only one side of a paper may be used.

> > (B) Photographs, illustrations, and tables may be reproduced by any method that results in a good copy of the original. If filed electronically, documents must be submitted in the same form as if submitted by mail, by third-party commercial carrier, i.e. color. Notice to the clerk of the supreme court must be given of anything other than black and white printed documents.

> **(2) Cover.** The cover of the appellant's brief must be blue; the appellee's red; an intervenor's or amicus curiae's green; a cross-appellee's and any reply brief gray. Covers of petitions for rehearing must be the same color as the petitioning party's principal brief. If the brief is filed electronically, the supreme court will affix the correct color cover. The front cover of a brief must contain:

> > (A) the number of the case;

> > (B) the name of the court;

> > (C) the title of the case (see Rule 3(d));

> > (D) the nature of the proceeding (e.g., Appeal from Summary Judgment) and the name of the court, agency, or board below;

> > (E) the title of the brief, identifying the party or parties for whom the brief is filed;

> > (F) the name, bar identification number, office address, and telephone number of counsel representing the party for whom the brief is filed.

> **(3) Binding.** The brief must be bound at the left in a secure manner that does not obscure the text and permits the brief to lie reasonably flat when open. If the brief is filed electronically, the supreme court will bind the brief.

> **(4) Paper Size, Line Spacing, and Margins.** The brief must be on 8½ by 11 inch paper. Margins must be at least one and one-half inch at the left and at least one inch on all other sides. Pages must be numbered at the bottom, either centered or at the right side. Page numbering must begin on the cover page with the arabic number 1 and continue consecutively to the end of the document.

> **(5) Typeface.** The typeface must be 12 point or larger with no more than 16 characters per inch. The text must be double-spaced, except headings and quotations may be single-spaced and indented. Footnotes must be double-spaced and must be in the same typeface as the text.

> **(6) Type Styles.** A brief must be set in a plain, roman style, although italics or boldface may be used for emphasis. Case names must be italicized or underlined.

> **(7) Paragraph Numbers.** Paragraphs must be numbered using arabic numerals in briefs. Reference to material in any document that contains paragraph numbers must be to the paragraph number.

> **(8) Page Limitations.**

> > **(A) Page Limit.** A principal brief may not exceed 38 pages, and a reply brief may not exceed 12 pages, excluding any addendum. Footnotes or endnotes must be included in the page count.

> > **(B) Page Limit for N.D.R.Civ.P. 54(b) Certification.** An argument on the appropriateness of N.D.R.Civ.P. 54(b) certification may not exceed 5 pages. Page limits for Rule 54(b) certification are in addition to the limits set forth in (8)(A).

**(b) Form of Other Documents.**

> **(1)** All paragraphs must be numbered in documents filed with the court except for exhibits, documents prepared before the action was commenced, or documents not prepared by the parties or court. Reference to material in any document that contains paragraph numbers must be to the paragraph number.

> **(2) Motion.** Rule 27 governs motion content. The form of all motion documents must comply with the requirements of paragraph (b)(4) below.

> **(3) Petition for Rehearing.** Rule 40 governs petition for rehearing content.

> **(4) Other Documents.** Any other document must be reproduced in the manner prescribed by subdivision (a), with the following exceptions:

> > (A) a cover is not necessary if the caption and signature page together contain the information required by subdivision (a); and

> > (B) Paragraph (a)(8) does not apply.

**(c) Non-compliance.** Documents not in compliance with this rule will not be filed.

**(d) Certificate of Compliance.** A brief must include a certificate by the attorney, or a self-represented party, that the document complies with the page limitation. The person preparing the certificate must rely on the page count of the filed electronic document. The certificate must state the number of pages in the document. An inaccurate certification may subject the filer to sanctions.

### N.D.R.App.P. 40 — Petition for Rehearing

**(a) Time to File; Content; Answer; Action by Court if Granted.**

> **(1) Time.** A petition for rehearing may be filed within 14 days after entry of judgment unless the time is shortened or enlarged by order.

> **(2) Contents.** The petition must state with particularity each point of law or fact that the petitioner believes the court has overlooked or misapprehended and must contain such argument in support of the petition as the petitioner desires to present. Oral argument is not permitted.

> **(3) Answer.** No answer to a petition for rehearing is permitted unless the court requests one. The length of an answer must comply with the page limitation in (b).

> **(4) Action by the Court.** If a petition for rehearing is granted, the court may do any of the following:

> > (A) make a final disposition of the case without reargument;

> > (B) restore it to the calendar for reargument or resubmission; or

> > (C) issue any other appropriate order.

**(b) Form of Petition; Length.** The petition must comply with Rule 32. The petition must include items required under Rule 28(b) that are applicable. A petition for rehearing may not exceed 10 pages, excluding any addendum. Footnotes and endnotes must be included in the page count.

**(c) Service and Filing.** The petition must be served and filed as Rule 25 and Rule 31(b) prescribe.

### N.D.R.App.P. 34 — Oral Argument

**(a) Request for Oral Argument.**

> **(1)** Oral argument generally will be scheduled unless:

> (A) a party has failed to file a timely brief;

> (B) a party has challenged the sufficiency of the findings of fact or the adequacy of the evidence supporting a finding of fact but has failed to provide the court with the related transcripts;

> (C) no request for oral argument has been made by any party as required by Rule 28(h);

> (D) the parties have agreed to waive oral argument; or

> (E) the court, in the exercise of its discretion, determines oral argument is unnecessary.

> **(2) Notice.** The clerk of the supreme court must advise all parties whether oral argument will be scheduled and, if so, the date, time, and place for argument.

> **(3) Participation in Oral Argument.** If oral argument is scheduled, a party that did not request oral argument in a principal brief must provide notice of an intent to participate. The notice must be served and filed within five days of service of the notice of oral argument under this rule.

**(b) Time Allowed for Argument; Postponement.** Regardless of the number of counsel on each side, the appellant will be allowed 30 minutes and the appellee will be allowed 20 minutes to present argument. The appellant may reserve up to 10 minutes for rebuttal by notifying the clerk of court immediately prior to argument. If only one side argues, argument will be limited to 20 minutes. Arguments on motions will be granted only in extraordinary circumstances. A motion to postpone the argument or to allow longer argument must be filed reasonably in advance of the hearing date. A party is not obliged to use all of the time allowed, and the court may terminate the argument at any time.

**(c) Order and Content of Argument.** The appellant opens and may reserve time to conclude the argument. The opening argument may include a fair statement of the case. Counsel must not read at length from briefs, records, or authorities.

**(d) Cross-Appeals and Separate Appeals.** Unless the court directs otherwise, a cross-appeal or separate appeal must be argued when the initial appeal is argued. Parties should not duplicate arguments.

**(e) Nonappearance of a Party.** If oral argument is scheduled and the appellee fails to appear, the court must hear appellant's argument. If the appellant fails to appear the court may hear the appellee's argument. If neither party appears, the case will be decided on the briefs, unless the court orders otherwise.

**(f) Submission on Briefs.** If no oral argument is scheduled under Rule 34(a)(1), the case will be submitted to the court on the briefs, unless the court directs otherwise.

### N.D.R.App.P. 14 — Identity Protection

(a) Form of Confidential References. In all filed documents, at oral argument and in opinions, the following individuals may not be referred to by name but may be referred to by the individual's initials:

> (1) the respondent in a mental health proceeding;

> (2) the respondent and members of the respondent's family in a conservatorship or guardianship proceeding;

> (3) the respondent in a juvenile proceeding;

> (4) the child and members of the child's family in a proceeding to terminate parental rights;

> (5) a minor child;

> (6) a victim or alleged victim of a sexual offense.

**(b) Other Privacy Protection.** Privacy protections in N.D.R.Ct. 3.4, in the North Dakota Century Code, and the North Dakota Constitution must be complied with in all filed documents, at oral argument and in opinions.

(c) Modification of Electronic Opinions.

> (1) Individual Names. On request, if the name of an individual eligible for protection under subdivision (a) appears in the electronic version of a specific appellate opinion, it must be replaced by the individual's initials and the opinion annotated with the words "Modified under N.D.R.App.P. 14."

> (2) Birth Dates. On request, if the full birth date of any individual appears in the electronic version of a specific appellate opinion, it may be replaced by the individual's birth year and the opinion annotated with the words "Modified under N.D.R.App.P. 14."

### N.D.R.App.P. 21 — Writs

(a) Petition, Filing, and Service.

> (1) A party seeking a writ must file a petition with the clerk of the supreme court and serve the petition on all parties to the proceeding in the district court. If requesting supervision, the party must also provide a copy to the district court judge.

> (2) The petition must state:

> > (A) the relief sought;

> > (B) the issues presented;

> > (C) the facts necessary to understand the issues presented; and

> > (D) the reasons why a writ should issue.

> (3) The petition must be accompanied by supporting documents. Supporting documents include any order or opinion, parts of the record, or other documents necessary to understand the matters set forth in the petition.

> > (A) If a petition is supported by briefs, declarations, or other documents, they must be served and filed with the petition.

> > (B) Supporting documents must be attached to the petition as exhibits. Any party may refer to an exhibit by setting forth in parentheses the capital letter "E" followed by the page number of the item in the petition followed by a colon and the specific line or paragraph where the information referred to is located, for example (E6:12:¶3).

(b) Action; Response to Petition; Briefs.

> (1) The court may act on a petition without a response. Otherwise, the court will fix a time for a response and may set a hearing. Unless the court requests, no response to a petition is permitted.

> (2) Two or more parties may respond jointly to a petition.

> (3) The court may invite or order the district court judge to respond to a petition or may invite an amicus curiae to do so.

(c) Form of Documents; Number of Copies. A petition and any response must contain all applicable items listed in Rule 28(b). All documents must conform to Rule 25, if applicable, and Rule 32. If filed by mail or third-party commercial carrier, an original must be filed. If filed electronically, one electronic copy of all documents must be filed.

(d) Fees. A docket fee is due at the time of filing, unless exempted under Rule 12. Any reproduction fee is due within seven days of filing.

### N.D.R.Ct. 3.4 — Privacy Protection for Filings Made with the Court

**(a) Definitions.**

> (1) "Confidential" means information in a court record as described in Rule 3.4(b)(1) or as ordered by the court, which is protected from public access but remains accessible to the court and the parties.

> (2) "Redact" means to remove confidential information from a court record to protect it.

> (3) "Sealed" means court records that are protected from public access, party access and access by unauthorized court personnel.

**(b) Redacted Filings.**

> (1) In General. Unless the court orders otherwise, a court record that contains an individual's social-security number, taxpayer-identification number, birth date, the name of an individual known to be a minor, or a financial-account number, including any credit, debit, investment or retirement account number, must be redacted to include only:

> > (A) the last four digits of the social-security number and taxpayer-identification number;

> > (B) the year of the individual's birth;

> > (C) the minor's initials;

> > (D) the last four digits of the financial-account number; and

> > (E) if a victim requests, all victim contact information must be redacted from documents to be filed with the court in a criminal or delinquency case.

> (2) Responsibility of Party or Nonparty to Redact. A party or nonparty making a filing with the court is solely responsible for ensuring that information required to be redacted under Rule 3.4(b)(1) does not appear on the filing.

> (3) Exemptions from Redaction Requirement. The redaction requirement does not apply to the following:

> > (A) any case record not accessible to the public under N.D. Sup. Ct. Admin. R. 41(3)(b)(6) and (7);

> > (B) the record of an administrative or agency proceeding;

> > (C) the record of a court or tribunal, if that record was not subject to the redaction requirement when originally filed;

> > (D) a filing covered by Rule 3.4(c);

> > (E) the name of an individual known to be a minor when the minor is a party, including:

> > > (i) in a non-criminal traffic case;

> > > (ii) in a change of name case;

> > > (iii) in a minor conservatorship case;

> > > (iv) named in a domestic violence protection order, disorderly conduct restraining order or sexual assault restraining order;

> > > (v) when the law requires the public disclosure of the minor's full name; or

> > > (vi) as otherwise ordered by the court.

> > (F) a defendant's date of birth in a court filing that is related to criminal matters, non-criminal motor vehicle and game and fish matters, and infractions.

**(c) Procedure to Protect from Public Access.**

> (1) Parties may not seal otherwise public documents by consent or by labeling them "sealed" or "confidential."

> (2) Motion. A party may move that a filing be designated "confidential" or "sealed." In its motion, the party must show that protection of the filing is justified under the factors listed in N.D. Sup. Ct. Admin. R. 41(4)(a). A motion to protect a filing from public access, the filing in question, and any supporting documents, must be filed as "confidential" until the court makes its ruling. A court record may not be designated "confidential" or "sealed" under these rules when reasonable redaction will adequately resolve the issues and protect the parties.

> (3) Court Order. On motion, or on its own, the court may order that a filing be designated "confidential" or "sealed". The court may later order that the filing be made public or order the person who made the filing to file a redacted version for the public record.

**(d) Filing a Confidential Information Form.**

> (1) In General. A filing that contains redacted information must be filed together with a confidential information form (shown in Appendix H) that identifies each item of redacted information and specifies an appropriate identifier that uniquely corresponds to each item listed. The form will be confidential except as to the parties or as the court may direct. Any reference in the case to a listed identifier will be construed to refer to the corresponding item of information.

> (2) Defendant Information. In a criminal case, the prosecutor must file a confidential information form that includes, when known, the defendant's social security number.

**(e) Non-conforming Documents.**

> (1) Waiver. A person waives the protection of Rule 3.4(b) as to the person's own information by filing it without redaction or without moving that the information be protected from public access.

> (2) An individual may apply to the court to redact the individual's own improperly included protected information from a filed document and the clerk of court must temporarily restrict access to the document pending order by the court.

> (3) If the court finds protected information was improperly included in a filed document, the court must restrict access to the document and may order a properly redacted document to be filed.

**(f) Sanctions.** If a filer fails to comply with this rule, the court, upon its own motion or upon the motion of any party, may impose sanctions. Sanctions may include:

> (1) an order requiring the pleading or other document to be returned to the party for redaction;

> (2) an order striking the document; and

> (3) an award of attorney's fees and costs to an individual required to bring a motion under Rule 3.4(e)(2).

### N.D.R.Ct. 11.6 — Medium-Neutral Case Citations

**(a) Citations Before January 1, 1997.** The initial citation of any published opinion of the supreme court released before January 1, 1997, contained in a brief, memorandum, or other document filed with any trial or appellate court and a citation in the table of cases in a brief must include a reference to the volume and page number of the North Western Reporter in which the opinion is published. Subsequent citations within a brief, memorandum, or other document must include the page number and sufficient reference to identify the initial citation.

**(b) Citations After January 1, 1997.** When available, initial citations must include the volume and initial page number of the North Western Reporter in which the opinion is published. The initial citation of any published opinion of the supreme court or court of appeals released on or after January 1, 1997, contained in a brief, memorandum, or other document filed with any trial or appellate court and the citation in the table of cases in a brief must also include a reference to the calendar year in which the decision was filed, followed by the court designation of "ND" for the supreme court or "ND App" for the court of appeals followed by a sequential number assigned by the clerk of the supreme court. A paragraph citation should be placed immediately following the sequential number assigned to the case. Subsequent citations within the brief, memorandum or other document must include the paragraph number and sufficient references to identify the initial citation.
