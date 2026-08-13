# JetBriefCheck

Checks appellate brief PDFs for compliance with the North Dakota Rules of Appellate Procedure and produces an HTML compliance report with a recommended action: **Accept**, **Correction Letter**, or **Reject**.

## Not an Official Court Product

JetBriefCheck is an independent, open-source project published by an individual in
a personal capacity as legal-educational software, consistent with Rule 3.1 of the
North Dakota Code of Judicial Conduct. It is not authorized, endorsed, or maintained
by the North Dakota Supreme Court, the Clerk of the Supreme Court, or the state court
system, and is being developed without court staff, equipment, or resources. Its
compliance report and recommended action (Accept, Correction Letter, or Reject) are
machine-generated and are not the determination of the Clerk or the Court — only the
Clerk and the Court decide whether a brief is accepted, returned for correction, or
rejected. Verify results against the current North Dakota Rules of Appellate
Procedure. It is not legal advice.

---
## Installing the Skill in Claude (Desktop)

<img width="541" height="318" alt="image" src="https://github.com/user-attachments/assets/037bf067-2090-4fbf-a33b-f810e7e96d08" />

Download the zip from the releases here, and in your desktop app, select Cowork and Customize. Then click Skills and the plus sign to add the zip skill file you just downloaded.

## Installing the Skill in Claude (Browser)

This section walks you through adding the JetBriefCheck to your Claude account so you can use it directly in a browser chat session. No programming knowledge is required.

### What You Need Before You Start

- A Claude account at [claude.ai](https://claude.ai) with a Pro, Team, or Enterprise plan (the skill requires the ability to upload files and use projects).
- The **`jetbriefcheck.zip`** file from the [latest release](https://github.com/jet52/jetbriefcheck/releases/latest). Click on `jetbriefcheck.zip` under Assets to download it.

### Step-by-Step Installation

#### 1. Open Claude and Create a New Project

1. Go to [claude.ai](https://claude.ai) and sign in.
2. In the left sidebar, click **Projects**.
3. Click **Create Project** (or the **+** button).
4. Give your project a name, such as "JetBriefCheck".
5. Click **Create**.

#### 2. Upload the Skill Files to Project Knowledge

> **Important — upload to the *project*, not to a chat.** Files uploaded to Project Knowledge are available in every chat you open inside that project. If you instead drag a file into a regular chat window, it only exists in that single conversation and disappears when you start a new one. Make sure you are adding the file through the project settings, not the chat input box.

1. Inside your new project, look for the **Project Knowledge** section (sometimes labeled "Project files" or accessible via a paperclip/attachment icon in the project settings).
2. Click **Upload** or **Add files**.
3. Select the **`jetbriefcheck.zip`** file you downloaded earlier.
4. Wait for the upload to finish. Claude will unpack and index the contents automatically.

The ZIP file contains everything the skill needs: the analysis scripts, the bundled North Dakota appellate rules, check definitions, and the skill instructions. As of v1.5.0, `SKILL.md` is fully self-contained — all rule text and check definitions are bundled inline, so the skill works even without PyMuPDF (falling back to semantic-only checks).

#### 3. Set the Project Instructions

1. In your project settings, find the **Custom Instructions** field (also called "System prompt" or "Project instructions").
2. Open the file `SKILL.md` from this repository (or extract it from the ZIP). Copy its entire contents.
3. Paste the contents into the Custom Instructions field.
4. Save the project settings.

These instructions tell Claude how to run the compliance analysis step by step whenever you upload a brief.

#### 4. Verify the Installation

1. Open a new chat inside the project.
2. Type: **"Are you ready to check a brief for compliance?"**
3. Claude should respond confirming it can analyze appellate briefs against the North Dakota Rules.

If Claude does not seem to recognize the skill, double-check that:
- The ZIP file was uploaded to the project (not just to a regular chat).
- The SKILL.md contents were pasted into the project's Custom Instructions.

### A Note on Scope

The skill lives inside the project you created — it is not available in other projects or in regular (non-project) chats. Claude does not currently offer a way to install a skill globally across your entire account.

In practice this isn't a limitation: just **open all your brief-checking chats inside this one project**. You can create as many chats as you like within a project, and every one of them will have access to the skill files and instructions automatically. Think of the project as a dedicated "JetBriefCheck" app that's always ready when you need it.

---

## Using the Skill

Once installed, using the skill is straightforward. You upload a PDF of an appellate brief, and Claude produces a detailed compliance report.

### Checking a Brief

1. **Open a chat** inside your JetBriefCheck project.
2. **Drag and drop** your brief PDF into the chat window (or click the attachment/paperclip icon and select the file).
3. **Tell Claude what to do.** You can simply say:

   > "Check this brief for compliance."

   Or be more specific if you know the brief type:

   > "Check this appellant brief for compliance."
   >
   > "This is an appellee brief. Please run a compliance check."
   >
   > "Check this reply brief."

4. **Wait for the analysis.** Claude will work through several phases automatically:
   - **Extraction** — reads the PDF and measures formatting (paper size, margins, fonts, spacing, page count).
   - **Mechanical checks** — compares measurements against Rule 32 requirements.
   - **Semantic checks** — reads the brief text and evaluates whether required sections are present and adequate (Table of Contents, Statement of Issues, Argument, etc.).
   - **Report generation** — combines all results into an HTML compliance report.

   > **Note:** If PyMuPDF is not available (e.g., in a claude.ai project), the skill automatically falls back to semantic-only checks. Claude reads the PDF directly and produces a text report, noting that mechanical checks (margins, fonts, spacing, page limits) were skipped.

5. **Review the results.** Claude will:
   - State the **recommended action**: Accept, Correction Letter, or Reject.
   - Summarize any **failed checks**, grouped by severity.
   - Provide a **downloadable HTML report** with full details.

### Understanding the Report

The HTML report has several sections:

- **Recommended Action** — a color-coded banner at the top:
  - **Green (Accept)** — the brief appears to comply with all rules.
  - **Yellow (Correction Letter)** — there are formatting issues that should be corrected, but the brief is not rejected outright.
  - **Red (Reject)** — there are serious compliance failures that warrant rejection.

- **Failed Checks** — grouped into three severity levels:
  - **Critical (Reject)** — violations that alone justify rejection (e.g., wrong paper size, font too small, over the page limit).
  - **Correction Required** — problems that should be fixed but don't rise to rejection level (e.g., margin too narrow, missing paragraph numbering).
  - **Advisory Notes** — minor issues or observations (e.g., oral argument notation not found, font style question).

- **Passed Checks** — an expandable section listing everything that passed. Click to expand.

- **Not Applicable / Not Determined** — two different things, both kept out of the recommendation. *Not applicable* means the check does not reach this brief type (amicus checks on an appellant brief). *Not determined* means the requirement is real but was never verified — the checker could not reach it, so it is unverified, not satisfied. **COV-001** (cover color) and **FMT-010** (footnote spacing) always land here: Rule 32 governs the physical cover and the footnotes, and a PDF records neither the cover stock nor a reliable footnote boundary. Both need a human eye on every brief. Others arrive here situationally — line spacing measurable on too few pages, a footer that cannot be read, a semantic check that returned no result.

- **Not Applicable** — checks that don't apply to this brief type (e.g., amicus-specific checks on an appellant brief).

Each failed check shows:
- A **check ID** (e.g., FMT-006) for reference.
- The **rule citation** (e.g., Rule 32(a)(5)), linked to the official rule text on ndcourts.gov.
- A **message** explaining what was found.
- **Details** with specifics — for font size issues, this includes a per-page breakdown showing which pages have undersized text and how many characters are affected.

### Tips for Best Results

- **Specify the brief type** if you know it. Auto-detection works for most appellant briefs but sometimes misidentifies appellee and reply briefs. Telling Claude the type up front avoids this.

- **Known measurement pitfalls to watch for.** These are calibrated against the sample of 23 briefs in `test-data/`; the counts below come from that sample, not from production volume.

  - **Font size (FMT-006)** — the report distinguishes two findings that need opposite corrections, so read the headline before acting.

    *Document-wide undersize.* When the **predominant** font size is itself below 12pt (9.7pt and 11.0pt both appear in the sample), the body type is small throughout and the per-page character counts are not a list of stray characters to hunt down. Five of the eight failures in the sample are this. Two causes produce it: the page was scaled down after composition (a "shrink to fit" print setting, a file-size reduction pass), or the brief was genuinely composed in small type. Line spacing separates them **in one direction only** — scaling shrinks type and leading together, so full-size leading beside small type proves the page was *not* scaled and the brief must be reset. The converse is not provable: a document composed at 10pt with matching leading is geometrically identical to a 12pt document scaled to 83%, and nothing in the PDF distinguishes them. The report says which case it is and flags the hedge; confirm against the source before advising a filer to refile rather than restyle.

    *Localized small type.* When the predominant size *is* 12pt, only scattered spans are undersized. Page numbers, footnote markers, superscripts, and small caps are classified separately from body text, and when the only noncompliant characters are incidental the severity drops to a note rather than a rejection. A REJECT here resting on a small body-character count is the case that still deserves an eyeball — the per-page breakdown shows exactly how many characters are involved.

  - **Line spacing (FMT-009)** — the old "probably a false positive" advice is retired. Before v1.6.0 the detector only measured gaps *within* a text block, and double-spaced lines land in one block each, so it measured almost nothing on exactly the briefs it was meant to check. It now also measures baseline-to-baseline between consecutive single-line blocks. In the sample only 2 of 23 briefs fail, and both look genuine — in one, the filer's own corrected refiling moves from 16.1pt to 27.5pt and passes. **Treat a spacing failure as probably real.**

    The report states measurement coverage ("measurable on 34 of 37 body pages"), because the median is only as good as the sample behind it. When fewer than half the body pages yield a measurement the check reports **undetermined** rather than concluding — in either direction. It previously reported "unable to measure line spacing; assumed compliant," which is how one sample brief passed at 20.5pt against a 20.0pt threshold on 2 of 7 pages while its corrected refiling measured 27.6pt on 13 of 13. Blank pages don't count against coverage.

  - **Bottom margin (FMT-005)** — page-number footers in the bottom 10% of the page are excluded from the margin, in every form filers actually use: bare numerals (`5`, `-5-`, `[5]`), roman numerals, and the labeled styles (`Page 5`, `Page 5 of 25`, `5 of 25`, `Page ii of 25`). Blocks with no extractable text — the empty text objects that scanned and re-imaged PDFs leave behind — are excluded everywhere on the page, since they occupy space but show no ink. Recognizing the labeled footers cleared 7 of the 9 FMT-005 failures in the sample with no new failures.

    A footer carrying anything beyond the number (a case caption, a docket number) is content and still counts against the margin, which is the intended behavior. The remaining sensitivity is the zone itself: a page number sitting just above the bottom 10% line is measured as body text.

  - **Page numbering (FMT-011, FMT-012)** — these share the footer recognizer above, with two deliberate differences from the margin check.

    *Detection reaches higher up the page.* Rule 32(a)(4) requires numbering "at the bottom" without saying how far up that reaches, and filers routinely set the number at 87–89% of page height — clear of the 1" margin but above the bottom-10% band the margin check uses. Detection covers the bottom 15%; margin exclusion still covers only the bottom 10%, so a number sitting inside the text area is still ordinary content for measurement. Aligning the two zones had reported 150 pages in the sample as unnumbered when the number was plainly printed.

    *A running footer counts as numbering.* Block detection sometimes merges the number into a longer footer (`Page 1 of 2 Brief in Support of Motion…`). That page is numbered, so FMT-011 accepts it — but the block is not purely a page number, so it still counts against the bottom margin. A bare leading numeral is not enough; the `Page`/`pg.` label is required, so ordinary prose beginning with a number is not mistaken for a footer.

    **Undetermined is a third outcome.** When the footer area holds an image or a text block with no extractable characters — the normal case for scanned and re-imaged briefs, which carry the number in the page image — the checker reports that it *could not determine* whether the page is numbered, rather than reporting it as unnumbered. These land in the "Not Applicable / Not Determined" section and cannot influence the recommendation. Confirm those by eye.

    FMT-012 (numbering starts at arabic "1" on the cover) is stricter than FMT-011 by design: a brief numbered `Page i of 25` passes FMT-011 — the pages *are* numbered — while FMT-012 correctly flags that the numbering does not start with arabic 1.

- **You can ask follow-up questions.** After the report is generated, you can ask Claude things like:
  - "Which pages have the font size issue?"
  - "Is the Table of Contents adequate?"
  - "What would need to be fixed for this brief to be accepted?"
  - "Can you re-check this as an appellee brief instead?"

- **You can check multiple briefs** in the same chat session. Just upload another PDF and ask Claude to check it.

### Brief Types Supported

| Brief Type | Description | Page Limit |
|------------|-------------|------------|
| Appellant | Opening brief filed by the appealing party | 38 pages |
| Appellee | Response brief filed by the opposing party | 38 pages |
| Reply | Reply to the appellee's brief | 12 pages |
| Cross-Appeal | Brief when both parties appeal | 38 pages |
| Amicus Curiae | "Friend of the court" brief | 19 pages |

### What Rules Are Checked

The checker evaluates compliance against these North Dakota rules:

**N.D.R.App.P. (Rules of Appellate Procedure):**
- **Rule 14** — Identity protection (initials for protected individuals)
- **Rule 21** — Writs (petition content and supporting documents)
- **Rule 28** — Required contents of briefs (sections, formatting of arguments, etc.)
- **Rule 29** — Requirements for amicus curiae briefs
- **Rule 30** — How to cite the record
- **Rule 32** — Physical formatting (paper size, margins, fonts, spacing, page limits, cover requirements)
- **Rule 34** — Oral argument notation on the cover

**N.D.R.Ct. (Rules of Court):**
- **Rule 3.4** — Privacy protection for personal identifiers in filings
- **Rule 11.6** — Medium-neutral case citations

---

## Developer Quick Start

```bash
# Set up the virtual environment
uv venv && uv pip install -r skill/requirements.txt
source .venv/bin/activate

# Deploy the Claude Code skill (symlinks this repo to ~/.claude/skills/)
python deploy_skill.py

# Run the web interface
python app.py

# Or use the Claude Code skill: /jetbriefcheck <path-to-pdf>
```

## Architecture

- **`skill/`** — Deployable skill content (symlinked to `~/.claude/skills/jetbriefcheck/`):
  - `SKILL.md` — Self-contained Claude Code skill definition (bundles all rules and check definitions inline; works with or without PyMuPDF)
  - `core/` — Shared analysis engine (PDF extraction, mechanical checks, semantic checks, report builder)
  - `scripts/` — CLI scripts for the Claude Code skill workflow (`check_brief.py`, `build_report.py`, `check_rule_freshness.py`)
  - `references/` — Check definitions, rules summary, and bundled rule text
- **`web/`** — Flask web interface (upload form, report viewer, JSON API)
- **`deploy_skill.py`** — Cross-platform script to deploy the skill to `~/.claude/skills/`

## Skill Deployment (Claude Code CLI)

The Claude Code skill (`/jetbriefcheck`) reads its files from `~/.claude/skills/jetbriefcheck/`. This repo is the single source of truth — `deploy_skill.py` copies the needed files into the skill directory.

```bash
python deploy_skill.py
```

Re-run after making changes in the repo to sync them to the deployed skill. Works on macOS, Linux, and Windows.

## Bundled Rules

The full text of the following rules is bundled in `skill/references/rules/`:

| File | Rule | Subject |
|------|------|---------|
| `rule-14.md` | N.D.R.App.P. 14 | Identity Protection |
| `rule-21.md` | N.D.R.App.P. 21 | Writs |
| `rule-28.md` | N.D.R.App.P. 28 | Briefs |
| `rule-29.md` | N.D.R.App.P. 29 | Brief of an Amicus Curiae |
| `rule-30.md` | N.D.R.App.P. 30 | References to the Record |
| `rule-32.md` | N.D.R.App.P. 32 | Form of Briefs and Other Documents |
| `rule-34.md` | N.D.R.App.P. 34 | Oral Argument |
| `rule-40.md` | N.D.R.App.P. 40 | Petition for Rehearing |
| `rule-3.4.md` | N.D.R.Ct. 3.4 | Privacy Protection for Filings |
| `rule-11.6.md` | N.D.R.Ct. 11.6 | Medium-Neutral Case Citations |

Rules were last verified current against ndcourts.gov on **2026-08-04**.

## Rule Freshness Checking

The skill automatically checks whether bundled rules are still current by comparing their effective dates against the live versions on ndcourts.gov. This check runs as part of the normal compliance workflow via `get_version_warnings()` in `skill/core/version_check.py`.

- **Cached**: Results are stored in `~/.cache/jetbriefcheck/rule_staleness.json` and reused for 90 days. No network calls on most runs.
- **Fail-open**: If ndcourts.gov is unreachable, the check silently succeeds.
- **Per-rule tracking**: Each rule's effective date is tracked independently. If any rule is amended, a warning is emitted identifying which rule changed and linking to the ndcourts.gov page.

To force a live check (bypassing the cache):

```bash
python3 skill/scripts/check_rule_freshness.py
```

When a rule is flagged as stale, update the bundled `.md` file, update `BUNDLED_EFFECTIVE_DATES` in `skill/core/version_check.py`, recompute hashes in `skill/version.json`, and bump `rules_verified`.

## Contributing

On a fresh clone, activate the local pre-push sensitive-content check:

```bash
git config --local core.hooksPath .githooks
```

It scans commits being pushed for likely ND court dockets, confidential-case
captions, and committed binaries. Bypass once with `git push --no-verify`.
