# JetBriefCheck — Iowa

Checks appellate brief PDFs for compliance with the **Iowa Rules of Appellate Procedure** and produces an HTML compliance report with a recommended action: **Accept**, **Correction Letter**, or **Reject**.

> **Fork notice**: This is an Iowa adaptation of [JetBriefCheck](https://github.com/jet52/jetbriefcheck), originally built for the North Dakota Rules of Appellate Procedure.

---

## Key Differences from North Dakota Version

| Feature | North Dakota | Iowa |
|---------|-------------|------|
| Length limits | Page-based (38 pages) | **Word-based (14,000 words)** |
| Font size | 12pt minimum | **14pt minimum** (proportional serif) |
| Left margin | 1.5 inches | **1 inch** (all sides equal) |
| Paragraph numbering | Required (arabic numerals) | Not required |
| TOC/TOA references | Paragraph references | **Page references** |
| Cover colors | Blue/red/gray/green | **None** (electronic filing) |
| Record citations | (R#:#) format | **(App. pp. ___) / (Tr. p. ___)** |
| Routing statement | Not required | **Required** (Supreme Court vs. Court of Appeals) |
| Preservation of error | In argument (optional) | **Required in each argument division** |

---

## Installing the Skill in Claude (Browser)

### What You Need Before You Start

- A Claude account at [claude.ai](https://claude.ai) with a Pro, Team, or Enterprise plan.
- The **`jetbriefcheck.zip`** file from the latest release.

### Step-by-Step Installation

1. Go to [claude.ai](https://claude.ai) and create a new **Project** (e.g., "JetBriefCheck Iowa").
2. Upload the `jetbriefcheck.zip` file to **Project Knowledge**.
3. Paste the contents of `SKILL.md` into the project's **Custom Instructions**.
4. Open a new chat and ask: **"Are you ready to check a brief for compliance?"**

---

## Using the Skill

1. **Open a chat** inside your JetBriefCheck project.
2. **Upload a brief PDF** (drag and drop or click attach).
3. **Tell Claude what to do**: "Check this brief for compliance."
4. **Review the results**: recommendation, failed checks, and downloadable HTML report.

### Brief Types Supported

| Brief Type | Description | Word Limit |
|------------|-------------|------------|
| Appellant | Opening brief filed by the appealing party | 14,000 words |
| Appellee | Response brief filed by the opposing party | 14,000 words |
| Reply | Reply to the appellee's brief | 7,000 words |
| Cross-Appeal | Brief when both parties appeal | 14,000 words |
| Amicus Curiae | "Friend of the court" brief | 7,000 words |

### What Rules Are Checked

The checker evaluates compliance against these Iowa rules:

- **Rule 6.903** — Format and contents of briefs (sections, formatting, type-volume)
- **Rule 6.904** — References in briefs (record citations, party names)
- **Rule 6.906** — Requirements for amicus curiae briefs
- **Rule 6.907** — Oral argument
- **Rule 6.1101** — Routing of cases (Supreme Court vs. Court of Appeals)

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
```

## Architecture

- **`core/`** — Shared analysis engine (PDF extraction, mechanical checks, semantic checks, report builder)
- **`scripts/`** — CLI scripts for the Claude Code skill workflow (`check_brief.py`, `build_report.py`)
- **`references/`** — Check definitions, rules summary, and bundled rule text
- **`web/`** — Flask web interface (upload form, report viewer, JSON API)
- **`SKILL.md`** — Self-contained Claude Code skill definition
- **`deploy_skill.py`** — Cross-platform script to deploy the skill to `~/.claude/skills/`

## Bundled Rules

The following rule summaries are bundled in `references/rules/`:

| File | Rule | Subject |
|------|------|---------|
| `rule-6.903.md` | Iowa R. App. P. 6.903 | Briefs (format and content) |
| `rule-6.904.md` | Iowa R. App. P. 6.904 | References in Briefs |
| `rule-6.906.md` | Iowa R. App. P. 6.906 | Brief of an Amicus Curiae |
| `rule-6.907.md` | Iowa R. App. P. 6.907 | Oral Argument |
| `rule-6.1101.md` | Iowa R. App. P. 6.1101 | Routing of Cases |
| `rule-1.422.md` | Confidential Filings | Privacy / Confidential Appendix |

> **Important**: The bundled rule files are summaries. You should verify them against the authoritative text at the [Iowa Legislature website](https://www.legis.iowa.gov/law/courtRules/courtRulesListings) (Chapter 6).

## TODO

- [ ] **Verify rule text**: Download the full PDF of Chapter 6 from the Iowa Legislature and verify all rule citations and thresholds against the authoritative text.
- [ ] **Update SKILL.md**: Rewrite the self-contained skill instructions for Iowa rules (currently still contains ND content).
- [ ] **Update mechanical checks**: Adapt `checks_mechanical.py` to use word-count limits instead of page limits, and update rule citations from ND to Iowa format.
- [ ] **Test with real Iowa briefs**: Obtain sample Iowa appellate briefs and validate the checker against them.
- [ ] **Compute rule hashes**: Once rule files are finalized, regenerate `version.json` with SHA-256 hashes.
- [ ] **Update deploy_skill.py**: Point to Iowa-specific repo URL if forked to a separate GitHub repository.
