# JetBriefCheck

Checks appellate brief PDFs for compliance with the North Dakota Rules of Appellate Procedure and produces an HTML compliance report with a recommended action: **Accept**, **Correction Letter**, or **Reject**. It also scans each filing for **concealed text** — text a machine reads that a person reading the page cannot see.

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
## Installing

Three ways in, in the order most people should try them.

### 1. As a plugin from jet-hub — recommended

JetBriefCheck is published through the [jet-hub](https://github.com/jet52/jet-hub)
marketplace, alongside the other JET legal tools. Add the marketplace once and
install the plugin from it; updates then come from the repository rather than
from a file you have to re-download.

```
/plugin marketplace add jet52/jet-hub
/plugin install jetbriefcheck@jet-hub
```

See the [jet-hub README](https://github.com/jet52/jet-hub#readme) for the
organization-wide install, which pushes the plugin to everyone on a Team or
Enterprise plan without each person installing it themselves.

> jet-hub pins each plugin to its latest **stable release tag** and re-syncs
> automatically, so an install tracks published releases rather than in-progress
> work on `main`. To pull an update through by hand:
> `/plugin marketplace update jet-hub` then `/plugin update`.

### 2. As a plugin, by direct upload (Cowork)

If you are not using the marketplace, download
**`jetbriefcheck-plugin-<version>.zip`** from the
[latest release](https://github.com/jet52/jetbriefcheck/releases/latest) and
upload it in Cowork under **Customize → Plugins**. This archive carries the
plugin manifest, which is what makes it install as a plugin rather than as a
bare skill.

### 3. As a standalone skill

<img width="541" height="318" alt="image" src="https://github.com/user-attachments/assets/037bf067-2090-4fbf-a33b-f810e7e96d08" />

Download **`jetbriefcheck-skill-<version>.zip`** from the
[latest release](https://github.com/jet52/jetbriefcheck/releases/latest), then in
the desktop app select **Cowork → Customize → Skills** and click **+** to add
the zip. Or unzip it into `~/.claude/skills/`.

This is the older path and is still supported. Prefer a plugin install if you
have the choice — it updates itself and it is how the tool is versioned.

> **Which zip?** `-plugin-` includes the manifest and installs as a plugin.
> `-skill-` is the skill directory alone. Downloading the wrong one is the
> usual cause of "it installed but Claude doesn't seem to know about it."

## Installing in Claude (Browser)

This section walks you through adding the JetBriefCheck to your Claude account so you can use it directly in a browser chat session. No programming knowledge is required.

### What You Need Before You Start

- A Claude account at [claude.ai](https://claude.ai) with a Pro, Team, or Enterprise plan (the skill requires the ability to upload files and use projects).
- The **`jetbriefcheck-skill-<version>.zip`** file from the [latest release](https://github.com/jet52/jetbriefcheck/releases/latest). Click it under Assets to download it. (Use the `-skill-` archive here, not `-plugin-`: a browser project takes the skill directory, not a plugin manifest.)

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
3. Select the **`jetbriefcheck-skill-<version>.zip`** file you downloaded earlier.
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

### Which model to use

**Opus is strongly recommended over Sonnet or Haiku.** This is based on initial
testing rather than a systematic benchmark, but the difference was clear enough
to be worth stating.

It helps to know which half of the work the choice affects, because it is not
the whole report:

- **Not model-dependent.** The mechanical checks (paper size, margins, fonts,
  line spacing, page limits, page numbering), the brief-type classification,
  and the concealed-text scan are deterministic Python measurements over the
  PDF. They produce the same answer on any model.
- **Model-dependent.** The 32 semantic checks — whether a Table of Contents is
  present and adequate, whether the Statement of Issues is really one, whether
  record citations identify their items, whether a conclusion states precise
  relief — are Claude reading the brief and exercising judgment. So is the
  narrative of the report, and so are any follow-up questions you ask about it.

**Fallback mode** (no PyMuPDF, e.g. a claude.ai project) is *entirely*
model-driven: Claude reads the PDF directly and every check is a judgment call,
with none of the deterministic floor underneath. That is where the choice of
model matters most.

Every report footer records the model that produced it, so runs stay comparable
as models change. If you compare models on the same brief, compare the semantic
checks; the mechanical ones will agree by construction.

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
   - **Concealed-text scan** — renders each page and checks whether every piece of text in the file is actually visible on it.
   - **Mechanical checks** — compares measurements against Rule 32 requirements.
   - **Semantic checks** — reads the brief text and evaluates whether required sections are present and adequate (Table of Contents, Statement of Issues, Argument, etc.).
   - **Report generation** — combines all results into an HTML compliance report.

   > **Note:** If PyMuPDF is not available (e.g., in a claude.ai project), the skill automatically falls back to semantic-only checks. Claude reads the PDF directly and produces a text report, noting that mechanical checks (margins, fonts, spacing, page limits) were skipped. **The concealed-text scan also does not run in fallback mode**, so the report says the brief was not checked for hidden text rather than implying it was checked and found clean.

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

- **Concealed Text** — text present in the file that a reader of the printed page cannot see: white or near-white type, an invisible render mode, full transparency, text covered by an opaque shape, type below 3pt, text positioned off the page, and invisible Unicode characters (including the tag block used to smuggle ASCII past a human reader, which is decoded for you).

  When something is found this section sits **directly under the recommendation banner, above the compliance findings** — a reader who stops at the banner still has to pass it. Each finding gives the page, the position, the point size, the mechanism (with the measured contrast ratio, where 1.00:1 is invisible), a character count and digest, and **the concealed text reproduced in full**. When nothing is found the section drops to the bottom as a one-line statement of what was checked, because silence would read as "nothing concealed" — which is the one thing an unrun scan cannot establish. A scan that ran and found nothing and a scan that never ran are reported differently.

  **It is not part of the compliance determination.** Concealed text violates none of the rules checked here, and the recommendation is computed before the section is loaded. The report describes precisely what was found and where, and stops: concealed text has innocent causes — production artifacts, redaction layers, template remnants — as well as culpable ones, and the assessment belongs to court staff.

  Concealed passages are removed from the text the semantic checks and the citation review read, so those passes see the document a person sees. The removal is disclosed in the report. **Limitation:** the scan does not read text hidden inside images.

- **Failed Checks** — grouped into three severity levels:
  - **Critical (Reject)** — violations that alone justify rejection (e.g., wrong paper size, font too small, over the page limit).
  - **Correction Required** — problems that should be fixed but don't rise to rejection level (e.g., margin too narrow, missing paragraph numbering).
  - **Advisory Notes** — minor issues or observations (e.g., oral argument notation not found, font style question).

- **Citation Review** *(when the ndlaw research tools are available)* — a separate, advisory section checking that each authority the brief cites **exists, is the case the brief names, and is quoted accurately**. It does *not* assess whether an authority supports the proposition it is cited for; that judgment is out of scope and is left to chambers.

  The verification is ndlaw's `check_draft`, which carries the citation parser and the North Dakota corpus. JetBriefCheck adds what `check_draft` cannot know — that it is reading a PDF extraction of a brief. It strips the page numbers extraction leaves inside quotations (which would otherwise report a correctly quoted brief as a misquotation), locates each finding by brief paragraph, and suppresses case-name differences that are only the reporter's own bookkeeping. A brief citing "Lucas v. Lucas" against a canonical caption of "Lucas v. Lucas (cross-reference w/20990001)" is correct; flagging it would be a false alarm on good work. Suppressed counts appear in the coverage line rather than vanishing.

  **It is not part of the compliance determination.** Nothing in it affects Accept / Correction Letter / Reject; the recommendation is computed before the section is loaded.

  When ndlaw is unavailable the section still appears and says no citation was verified, rather than vanishing and leaving the impression the citations were checked and found sound.

- **Passed Checks** — an expandable section listing everything that passed. Click to expand.

- **Not Applicable / Not Determined** — two different things, both kept out of the recommendation. *Not applicable* means the check does not reach this brief type (amicus checks on an appellant brief). *Not determined* means the requirement is real but was never verified — the checker could not reach it, so it is unverified, not satisfied. **COV-001** (cover color) always lands here: Rule 32(a)(2) governs the physical cover, which a PDF does not record, so it needs a human eye on every brief. Others arrive here situationally — line spacing measurable on too few pages, a footer that cannot be read, a semantic check that returned no result.

- **Not Applicable** — checks that don't apply to this brief type (e.g., amicus-specific checks on an appellant brief).

Each failed check shows:
- A **check ID** (e.g., FMT-006) for reference.
- The **rule citation** (e.g., Rule 32(a)(5)), linked to the official rule text on ndcourts.gov.
- A **message** explaining what was found.
- **Details** with specifics — for font size issues, this includes a per-page breakdown showing which pages have undersized text and how many characters are affected.

### Tips for Best Results

- **Specify the brief type** if the cover is unusual. Auto-detection reads the brief's own title line ("BRIEF OF APPELLANT", "BRIEF OF RESPONDENT – APPELLANT") and resolves compound designations by their trailing appellate role, since a cover names the trial-court role first. It is correct on all 22 labelled briefs in the local sample. If the cover carries no such title, the checker reports the type as unknown rather than guessing from the caption — both parties appear there — and an unknown type means the page limit and the brief-type-specific section checks are skipped — they are reported as *not determined* rather than passed or not applicable, so the report shows what went unverified. Telling Claude the type up front avoids that.

- **Known measurement pitfalls to watch for.** These are calibrated against the sample of 23 briefs in `test-data/`; the counts below come from that sample, not from production volume.

  - **Font size (FMT-006)** — the report distinguishes two findings that need opposite corrections, so read the headline before acting.

    *Document-wide undersize.* When the **predominant** font size is itself below 12pt (9.7pt and 11.0pt both appear in the sample), the body type is small throughout and the per-page character counts are not a list of stray characters to hunt down. Five of the eight failures in the sample are this. Two causes produce it: the page was scaled down after composition (a "shrink to fit" print setting, a file-size reduction pass), or the brief was genuinely composed in small type. Line spacing separates them **in one direction only** — scaling shrinks type and leading together, so full-size leading beside small type proves the page was *not* scaled and the brief must be reset. The converse is not provable: a document composed at 10pt with matching leading is geometrically identical to a 12pt document scaled to 83%, and nothing in the PDF distinguishes them. The report says which case it is and flags the hedge; confirm against the source before advising a filer to refile rather than restyle.

    *Localized small type.* When the predominant size *is* 12pt, only scattered spans are undersized. Page numbers, footnote markers, superscripts, and small caps are classified separately from body text, and when the only noncompliant characters are incidental the severity drops to a note rather than a rejection. A REJECT here resting on a small body-character count is the case that still deserves an eyeball — the per-page breakdown shows exactly how many characters are involved.

  - **Line spacing (FMT-009)** — the old "probably a false positive" advice is retired. Before v1.6.0 the detector only measured gaps *within* a text block, and double-spaced lines land in one block each, so it measured almost nothing on exactly the briefs it was meant to check. It now also measures baseline-to-baseline between consecutive single-line blocks. In the sample only 2 of 23 briefs fail, and both look genuine — in one, the filer's own corrected refiling moves from 16.1pt to 27.5pt and passes. **Treat a spacing failure as probably real.**

    The report also locates **single-spaced passages** — "Single-spaced passages of 3+ lines: 11 (longest 23 lines, page 8)" — with pages named for runs of 8+ lines, longer than a typical block quotation. These are reported, never scored: Rule 32(a)(5) permits headings and quotations to be single-spaced, and nothing in a PDF's geometry separates a permitted passage from a defective one. The median verdict catches a brief single-spaced throughout; this catches the isolated block it cannot see, and leaves the call to you. The cover is excluded, since a caption block is single-spaced by convention.

    The report states measurement coverage ("measurable on 34 of 37 body pages"), because the median is only as good as the sample behind it. When fewer than half the body pages yield a measurement the check reports **undetermined** rather than concluding — in either direction. It previously reported "unable to measure line spacing; assumed compliant," which is how one sample brief passed at 20.5pt against a 20.0pt threshold on 2 of 7 pages while its corrected refiling measured 27.6pt on 13 of 13. Blank pages don't count against coverage.

  - **Bottom margin (FMT-005)** — page-number footers in the bottom 10% of the page are excluded from the margin, in every form filers actually use: bare numerals (`5`, `-5-`, `[5]`), roman numerals, and the labeled styles (`Page 5`, `Page 5 of 25`, `5 of 25`, `Page ii of 25`). Blocks with no extractable text — the empty text objects that scanned and re-imaged PDFs leave behind — are excluded everywhere on the page, since they occupy space but show no ink. Recognizing the labeled footers cleared 7 of the 9 FMT-005 failures in the sample with no new failures.

    A footer carrying anything beyond the number (a case caption, a docket number) is content and still counts against the margin, which is the intended behavior. The remaining sensitivity is the zone itself: a page number sitting just above the bottom 10% line is measured as body text.

  - **Page numbering (FMT-011, FMT-012)** — these share the footer recognizer above, with two deliberate differences from the margin check.

    *Detection reaches higher up the page.* Rule 32(a)(4) requires numbering "at the bottom" without saying how far up that reaches, and filers routinely set the number at 87–89% of page height — clear of the 1" margin but above the bottom-10% band the margin check uses. Detection covers the bottom 15%; margin exclusion still covers only the bottom 10%, so a number sitting inside the text area is still ordinary content for measurement. Aligning the two zones had reported 150 pages in the sample as unnumbered when the number was plainly printed.

    *A running footer counts as numbering.* Block detection sometimes merges the number into a longer footer (`Page 1 of 2 Brief in Support of Motion…`). That page is numbered, so FMT-011 accepts it — but the block is not purely a page number, so it still counts against the bottom margin. A bare leading numeral is not enough; the `Page`/`pg.` label is required, so ordinary prose beginning with a number is not mistaken for a footer.

    **Undetermined is a third outcome.** When the footer area holds an image or a text block with no extractable characters — the normal case for scanned and re-imaged briefs, which carry the number in the page image — the checker reports that it *could not determine* whether the page is numbered, rather than reporting it as unnumbered. These land in the "Not Applicable / Not Determined" section and cannot influence the recommendation. Confirm those by eye.

    FMT-012 (numbering starts at arabic "1" on the cover) is stricter than FMT-011 by design: a brief numbered `Page i of 25` passes FMT-011 — the pages *are* numbered — while FMT-012 correctly flags that the numbering does not start with arabic 1.

  - **Concealed text** — the trigger is *visibility*, never the mechanism, and that distinction is what makes the check usable.

    Two independent tests, both needed. A **glyph test** compares the text's colour against the measured background of the region it occupies (below a 1.5:1 contrast ratio it cannot be made out; ordinary black on white is 21:1) together with its opacity. A **region test** renders the page and asks whether any ink appeared in the text's bounding box at all. Neither subsumes the other: region ink alone misses a white payload laid *over* existing body text, because the neighbouring words supply the ink; colour alone misses perfectly black text covered by a white rectangle.

    **An invisible render mode is never a finding by itself.** Every OCR'd scan carries a full invisible-text layer over the page image, and those words are visible — they *are* the page image. Three of the 23 briefs in `test-data/` are such scans, and triggering on the render mode flagged 100% of their spans, 21,867 in one brief alone. A page whose text is predominantly in that mode is identified as an OCR layer and reported as context, not as concealment; the sub-legible trigger is also suppressed there, because OCR assigns nonsense point sizes to specks and dust.

    Calibrated over the sample's 50,735 text spans: **22 of 23 briefs report nothing.** The 23rd is a misassembled scan whose text layer largely does not correspond to its pages; it is labelled as such, and its findings are still listed in full — suppressing them is precisely what someone hiding a payload would want. Two further floors keep ordinary typography quiet: the measured box excludes whitespace and is padded for glyphs that paint outside it (an underscore does, and unpadded every signature line in the sample read as concealed text), and a finding must clear a length *and* a letters-and-digits floor **after** adjacent runs are merged — so a payload split character-by-character to duck the floor still reaches it.

    *Why this exists:* in *Elliott v. N.Y. Bariatric Group, LLC*, a Connecticut Superior Court judge found a self-represented plaintiff had hidden instructions to an AI in white, tiny-point text in a filing, and revoked the plaintiff's e-filing privileges. The court's objection was not that a model might obey them but that the text was a concealed communication to the decision-maker, pleaded outside the other side's knowledge — a filing-integrity problem whether or not any software ever reads the brief. (As reported at [Volokh Conspiracy](https://reason.com/volokh/2026/08/13/court-faults-self-represented-plaintiff-for-including-hidden-prompt-injection-in-court-filing/), Aug. 13, 2026.)

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

# Deploy the Claude Code skill (COPIES skill/ into ~/.claude/skills/jetbriefcheck/).
# Only needed on machines without the symlink setup — it deletes an existing
# symlink at that path, so if you develop against a symlinked skill dir, skip this.
python deploy_skill.py

# Run the tests
make test

# Build release artifacts
make package        # plugin zip (the primary artifact)
make package-all    # plugin zip + standalone skill zip
make version-check  # assert version.json, plugin.json and SKILL.md agree

# Run the web interface
python app.py

# Or use the Claude Code skill: /jetbriefcheck <path-to-pdf>
```

### Packaging notes

Two archives come out of a build, and the difference matters to installers:

| Artifact | Contains | Installs as |
|---|---|---|
| `jetbriefcheck-plugin-<version>.zip` | `.claude-plugin/plugin.json` + `skill/` | A plugin (Cowork upload, marketplace) |
| `jetbriefcheck-skill-<version>.zip` | `jetbriefcheck/` (the skill tree alone) | A standalone skill |

Always package through the Makefile. `zip -r` **adds to** an existing archive
rather than replacing it, so every public target cleans first; the retired
`build_zip.sh` did not, and local builds had been quietly accumulating
repo-root files that were never part of the skill. `build_zip.sh` now just
delegates to `make package-all`.

Note how an update reaches plugin users: jet-hub pins each plugin to a
**release tag**, and its sync workflow bumps that pin to the latest stable
release every 30 minutes. So a build ships when the GitHub release is
**published** — pushing `main` alone ships nothing, and a release left as a
draft or marked prerelease is skipped by the sync entirely. `make release`
does the whole sequence.

## Architecture

- **`skill/`** — Deployable skill content (symlinked to `~/.claude/skills/jetbriefcheck/`):
  - `SKILL.md` — Self-contained Claude Code skill definition (bundles all rules and check definitions inline; works with or without PyMuPDF)
  - `core/` — Shared analysis engine (PDF extraction, concealed-text scan, mechanical checks, semantic checks, report builder)
  - `scripts/` — CLI scripts for the Claude Code skill workflow (`check_brief.py`, `build_report.py`, `check_rule_freshness.py`)
  - `references/` — Check definitions, rules summary, and bundled rule text
- **`web/`** — Flask web interface (upload form, report viewer, JSON API)
- **`deploy_skill.py`** — Cross-platform script to deploy the skill to `~/.claude/skills/`

## Skill Deployment (Claude Code CLI)

The Claude Code skill (`/jetbriefcheck`) reads its files from `~/.claude/skills/jetbriefcheck/`. This repo is the single source of truth — `deploy_skill.py` copies the needed files into the skill directory.

If instead you symlink `~/.claude/skills/jetbriefcheck` to this repo's `skill/`, editing the repo updates the live skill with no deploy step. **Do not run `deploy_skill.py` on such a machine** — it removes the symlink and replaces it with a copy, after which repo edits stop taking effect.

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
