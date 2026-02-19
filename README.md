# Appellate Brief Compliance Checker

Checks appellate brief PDFs for compliance with the North Dakota Rules of Appellate Procedure and produces an HTML compliance report with a recommended action: **Accept**, **Correction Letter**, or **Reject**.

---

## Installing the Skill in Claude (Browser)

This section walks you through adding the Brief Compliance Checker to your Claude account so you can use it directly in a browser chat session. No programming knowledge is required.

### What You Need Before You Start

- A Claude account at [claude.ai](https://claude.ai) with a Pro, Team, or Enterprise plan (the skill requires the ability to upload files and use projects).
- The **`brief-compliance.zip`** file from this repository. You can download it from the repository's file list by clicking on `brief-compliance.zip` and then clicking the download button.

### Step-by-Step Installation

#### 1. Open Claude and Create a New Project

1. Go to [claude.ai](https://claude.ai) and sign in.
2. In the left sidebar, click **Projects**.
3. Click **Create Project** (or the **+** button).
4. Give your project a name, such as "Brief Compliance Checker".
5. Click **Create**.

#### 2. Upload the Skill Files to Project Knowledge

> **Important — upload to the *project*, not to a chat.** Files uploaded to Project Knowledge are available in every chat you open inside that project. If you instead drag a file into a regular chat window, it only exists in that single conversation and disappears when you start a new one. Make sure you are adding the file through the project settings, not the chat input box.

1. Inside your new project, look for the **Project Knowledge** section (sometimes labeled "Project files" or accessible via a paperclip/attachment icon in the project settings).
2. Click **Upload** or **Add files**.
3. Select the **`brief-compliance.zip`** file you downloaded earlier.
4. Wait for the upload to finish. Claude will unpack and index the contents automatically.

The ZIP file contains everything the skill needs: the analysis scripts, the bundled North Dakota appellate rules, check definitions, and the skill instructions.

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

In practice this isn't a limitation: just **open all your brief-checking chats inside this one project**. You can create as many chats as you like within a project, and every one of them will have access to the skill files and instructions automatically. Think of the project as a dedicated "Brief Compliance Checker" app that's always ready when you need it.

---

## Using the Skill

Once installed, using the skill is straightforward. You upload a PDF of an appellate brief, and Claude produces a detailed compliance report.

### Checking a Brief

1. **Open a chat** inside your Brief Compliance Checker project.
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

- **Not Applicable** — checks that don't apply to this brief type (e.g., amicus-specific checks on an appellant brief).

Each failed check shows:
- A **check ID** (e.g., FMT-006) for reference.
- The **rule citation** (e.g., Rule 32(a)(5)), linked to the official rule text on ndcourts.gov.
- A **message** explaining what was found.
- **Details** with specifics — for font size issues, this includes a per-page breakdown showing which pages have undersized text and how many characters are affected.

### Tips for Best Results

- **Specify the brief type** if you know it. Auto-detection works for most appellant briefs but sometimes misidentifies appellee and reply briefs. Telling Claude the type up front avoids this.

- **Known false positives to watch for:**
  - **Font size (FMT-006)**: Page numbers, footnote markers, and superscripts are often smaller than 12pt. The report now categorizes these separately (body text vs. header/footer vs. superscript) so you can see whether the issue is real body text or just incidental small characters. If the only noncompliant characters on a page are in the header/footer or superscript categories, the severity is downgraded to a note rather than a rejection.
  - **Line spacing (FMT-009)**: The spacing detector can misread certain PDF encodings. If the brief was prepared in a standard word processor with double spacing selected, a spacing failure is likely a false positive.
  - **Bottom margin (FMT-005)**: Page numbers at the bottom of the page are measured as content, which makes the bottom margin appear smaller than it really is.

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

- **Rule 28** — Required contents of briefs (sections, formatting of arguments, etc.)
- **Rule 29** — Requirements for amicus curiae briefs
- **Rule 30** — How to cite the record
- **Rule 32** — Physical formatting (paper size, margins, fonts, spacing, page limits, cover requirements)
- **Rule 34** — Oral argument notation on the cover
- **Rule 3.4** — Privacy protection for personal identifiers in filings

---

## Developer Quick Start

```bash
# Set up the virtual environment
uv venv && uv pip install -r requirements.txt
source .venv/bin/activate

# Deploy the Claude Code skill (symlinks this repo to ~/.claude/skills/)
python deploy_skill.py

# Run the web interface
python app.py

# Or use the Claude Code skill: /brief-compliance <path-to-pdf>
```

## Architecture

- **`core/`** — Shared analysis engine (PDF extraction, mechanical checks, semantic checks, report builder)
- **`scripts/`** — CLI scripts for the Claude Code skill workflow (`check_brief.py`, `build_report.py`)
- **`references/`** — Check definitions, rules summary, and bundled rule text
- **`web/`** — Flask web interface (upload form, report viewer, JSON API)
- **`SKILL.md`** — Claude Code skill definition (deployed via symlink)
- **`deploy_skill.py`** — Cross-platform script to deploy the skill to `~/.claude/skills/`

## Skill Deployment (Claude Code CLI)

The Claude Code skill (`/brief-compliance`) reads its files from `~/.claude/skills/brief-compliance/`. This repo is the single source of truth — `deploy_skill.py` copies the needed files into the skill directory.

```bash
python deploy_skill.py
```

Re-run after making changes in the repo to sync them to the deployed skill. Works on macOS, Linux, and Windows.

## Bundled Rules

The full text of the following rules is bundled in `references/rules/`:

| File | Rule | Subject |
|------|------|---------|
| `rule-28.md` | N.D.R.App.P. 28 | Briefs |
| `rule-29.md` | N.D.R.App.P. 29 | Brief of an Amicus Curiae |
| `rule-30.md` | N.D.R.App.P. 30 | References to the Record |
| `rule-32.md` | N.D.R.App.P. 32 | Form of Briefs and Other Documents |
| `rule-34.md` | N.D.R.App.P. 34 | Oral Argument |
| `rule-3.4.md` | N.D.R.Ct. 3.4 | Privacy Protection for Filings |

Rules were last copied from the authoritative source on **2026-02-17**.

## TODO

- [ ] **Rule freshness check**: Add a feature (script or startup check) that compares the bundled rule files against the current versions at ndcourts.gov to detect whether any rules have been amended since the bundled copies were last updated. Candidate URLs:
  - https://www.ndcourts.gov/legal-resources/rules/ndrappp/28
  - https://www.ndcourts.gov/legal-resources/rules/ndrappp/29
  - https://www.ndcourts.gov/legal-resources/rules/ndrappp/32
  - https://www.ndcourts.gov/legal-resources/rules/ndrappp/34
  - https://www.ndcourts.gov/legal-resources/rules/ndrct/3-4
