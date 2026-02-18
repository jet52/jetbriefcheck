#!/usr/bin/env python3
"""Deploy the brief-compliance skill to Claude Code's skills directory.

Copies skill files (SKILL.md, scripts/, references/, core/, .venv/, requirements.txt)
from this repo into ~/.claude/skills/brief-compliance/.

Works on macOS, Linux, and Windows — no symlinks required.

Run from anywhere:
    python deploy_skill.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SKILL_NAME = "brief-compliance"
COPY_ITEMS = ["SKILL.md", "scripts", "references", "core", "requirements.txt", ".venv"]


def _get_skills_dir() -> Path:
    """Return Claude Code's skills directory, creating it if needed."""
    skills_dir = Path.home() / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    target = _get_skills_dir() / SKILL_NAME

    if not (repo_root / "SKILL.md").exists():
        print("Error: SKILL.md not found in repo root.", file=sys.stderr)
        sys.exit(1)

    # Remove old symlink if present (migration from previous deploy method)
    if target.is_symlink():
        print(f"Removing old symlink: {target}")
        target.unlink()

    target.mkdir(parents=True, exist_ok=True)

    for item_name in COPY_ITEMS:
        src = repo_root / item_name
        dst = target / item_name
        if not src.exists():
            continue
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        print(f"  Copied: {item_name}")

    print(f"\nDeployed to {target}")
    print("Re-run after repo changes to sync.")


if __name__ == "__main__":
    main()
