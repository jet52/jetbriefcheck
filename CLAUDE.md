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
  - **FMT-009 line spacing** — measured across split blocks since v1.6.0; failures are usually real. Risk is the opposite: thin page coverage can hide a single-spaced brief
  - **FMT-005 / FMT-011 / FMT-012** — share one page-number footer recognizer (`_page_number_value` in `pdf_extract.py`); residual gap is page numbers outside the bottom 10% zone, and scanned briefs whose numbers are images
- Test data in `test-data/` (~76 sample PDFs; 23 are briefs, the rest generated reports)
- Skill deploys to `~/.claude/skills/jetbriefcheck/`
