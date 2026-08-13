# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Checks appellate brief PDFs for compliance with North Dakota Rules of Appellate Procedure. Analyzes formatting (margins, fonts, spacing, page limits) and semantic content (required sections). Produces HTML compliance reports with recommendations: Accept, Correction Letter, or Reject. Also deployable as a Claude Code skill.

## Commands

```bash
# Setup
uv venv && uv pip install -r skill/requirements.txt
source .venv/bin/activate

# Run web interface
python app.py

# Deploy as Claude Code skill
python deploy_skill.py

# Run tests
pytest tests/
```

## Architecture

- **`app.py`** — Flask entry point (web interface)
- **`skill/`** — Deployable skill content (symlinked to `~/.claude/skills/jetbriefcheck/`):
  - `SKILL.md` — Claude Code skill workflow definition
  - `core/` — Analysis engine:
    - `pdf_extract.py` — Extract text/images, measure formatting via PyMuPDF
    - `brief_classifier.py` — Detect brief type (appellant, appellee, reply, amicus, petition for rehearing)
    - `checks_mechanical.py` — Paper size, margins, fonts, spacing, page limits
    - `checks_semantic.py` — Required sections, adequate content
    - `report_builder.py` — Generate HTML compliance report
    - `models.py` — Data structures for checks and results
    - `recommender.py` — Accept/Correction Letter/Reject determination
  - `scripts/` — CLI entry points for skill pipeline
  - `references/rules/` — Bundled rule text: N.D.R.App.P. 14, 21, 28, 29, 30, 32, 34, 40; N.D.R.Ct. 3.4, 11.6
- **`web/`** — Flask templates and static assets

## Key Details

- Python 3.9+, PyMuPDF >= 1.24.0
- Optional Anthropic API key for AI-enhanced analysis
- Measurement pitfalls (see README "Known measurement pitfalls" for detail):
  - **FMT-006 font size** — splits document-wide undersize (predominant size itself below 12pt) from scattered spans; leading/font ratio rules *out* page scaling but cannot prove it (see `_explain_document_wide_undersize`). Headers/footers/superscripts/small caps are categorized and downgraded already
  - **FMT-009 line spacing** — measured across split blocks since v1.6.0; failures are usually real. Reports measurement coverage, and returns **undetermined** below `MIN_SPACING_COVERAGE_PCT` (50%) instead of the old "assumed compliant". Also counts single-spaced runs (`_find_single_spaced_runs`) and reports them **without scoring** — Rule 32(a)(5) permits single-spaced headings and quotations, so a run is evidence, not a finding; never wire these into the verdict
  - **FMT-005 / FMT-011 / FMT-012** — share one page-number footer recognizer (`_page_number_value` in `pdf_extract.py`), but two zones: `_MARGIN_FOOTER_ZONE` (0.90) for what may sit inside the bottom margin, `_PAGE_NUMBER_ZONE` (0.85) for what counts as numbering. FMT-011/012 report **undetermined** (`applicable=False`, so it cannot drive the recommendation) when the footer holds an image or unreadable text — never "unnumbered"
- **Two execution paths for semantic checks — don't conflate them.**
  - *Skill path* (how it runs under a Claude subscription): SKILL.md has Claude evaluate the
    checks directly and write `<stem>-semantic.json`; `build_report.py` merges it. **No API
    key, and `anthropic` is not installed** — `skill/requirements.txt` is PyMuPDF only, so
    nothing on this path may import `checks_semantic`. Shared check definitions live in
    `core/semantic_definitions.py` (pure data) for exactly this reason.
  - *API path* (Flask app, CLI with a key): `core/checks_semantic.run_semantic_checks`.
- **COV-001** (cover color) is *structurally* undeterminable — Rule 32(a)(2) governs the physical cover,
  which a PDF does not record. It reports undetermined on every brief and must never be marked passed; the
  message still names the required color so the manual check is actionable.
- **FMT-010 (footnote spacing) is retired**, not missing. Rule 32(a)(5) imposes no requirement on footnotes
  distinct from the body — footnotes are part of "the text" — so FMT-006/008/009 measuring all text cover it.
  See "Retired Check IDs" in `check-definitions.md`; do not reassign the id.
- On both paths, a check that was not evaluated is reported **undetermined**
  (`applicable=False`), never passed — omitted from the semantic JSON on the skill path,
  or unparseable/absent from the API response on the other. Never reintroduce a
  `passed=True` fallback for unevaluated checks; the "Passed Checks" list must not contain
  fiction.
- **Brief-type classification** (`brief_classifier.py`): a cover names the trial-court role first and the
  appellate role last, so a compound designation resolves on its **trailing** role (`_designation_role`);
  "respondent - appellant" is an appellant brief. The "brief of X" window takes no closing delimiter —
  `_normalize` collapses newlines, so requiring one silently failed on plain "BRIEF OF APPELLANT".
  `UNKNOWN` is a real outcome, not a bug: the caption names both parties, so with no title line the
  classifier declines rather than guessing. When the type is UNKNOWN the 15 type-gated semantic checks
  plus PG-001/REC-001 report **not determined**, never "not applicable" — use `gated_check_result`
  (`semantic_definitions.py`), which both execution paths share.
- **Citation grounding** (`core/citations.py`, SKILL.md Phase 2C): extraction and scoping are
  deterministic and dependency-free; retrieval runs in the skill phase via ndlaw MCP and comes back as
  `<stem>-citations.json`. **Advisory only** — findings are a `CitationReview` on `ComplianceReport`,
  never `CheckResult`s, and `build_report.py` loads them only after the recommendation is fixed. Never
  route them through `results`. When ndlaw is unavailable, write the file with
  `"ndlaw_available": false` rather than skipping it.
- Test data in `test-data/` (~76 sample PDFs; 23 are briefs, the rest generated reports)
- Live API tests are opt-in: `JETBRIEFCHECK_LIVE_API=1 pytest -k Live` (needs
  `ANTHROPIC_API_KEY`); they use fabricated brief text, never real case content
- Skill deploys to `~/.claude/skills/jetbriefcheck/`
