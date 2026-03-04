# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Checks appellate brief PDFs for compliance with North Dakota Rules of Appellate Procedure. Analyzes formatting (margins, fonts, spacing, page limits) and semantic content (required sections). Produces HTML compliance reports with recommendations: Accept, Correction Letter, or Reject. Also deployable as a Claude Code skill.

## Commands

```bash
# Setup
uv venv && uv pip install -r requirements.txt
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
- **`core/`** — Analysis engine:
  - `pdf_extract.py` — Extract text/images, measure formatting via PyMuPDF
  - `brief_classifier.py` — Detect brief type (appellant, appellee, reply, amicus)
  - `checks_mechanical.py` — Paper size, margins, fonts, spacing, page limits
  - `checks_semantic.py` — Required sections, adequate content
  - `report_builder.py` — Generate HTML compliance report
  - `models.py` — Data structures for checks and results
  - `recommender.py` — Accept/Correction Letter/Reject determination
- **`references/rules/`** — Bundled ND appellate rule text (Rules 28, 29, 30, 32, 34, 3.4)
- **`web/`** — Flask templates and static assets
- **`SKILL.md`** — Claude Code skill workflow definition

## Key Details

- Python 3.9+, PyMuPDF >= 1.24.0
- Optional Anthropic API key for AI-enhanced analysis
- Known false positives: font size (headers/footers/superscripts), line spacing (encoding issues), bottom margins (page numbers)
- Test data in `test-data/` (~76 sample PDFs)
- Skill deploys to `~/.claude/skills/jetbriefcheck/`
