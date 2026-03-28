#!/usr/bin/env python3
"""Deploy the jetbriefcheck skill to Claude Code's skills directory.

Copies skill/ contents into ~/.claude/skills/jetbriefcheck/.
Only needed on machines without the symlink setup.

Run from anywhere:
    python deploy_skill.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SKILL_NAME = "jetbriefcheck"


def _get_skills_dir() -> Path:
    """Return Claude Code's skills directory, creating it if needed."""
    skills_dir = Path.home() / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    skill_src = repo_root / "skill"
    target = _get_skills_dir() / SKILL_NAME

    if not (skill_src / "SKILL.md").exists():
        print("Error: skill/SKILL.md not found.", file=sys.stderr)
        sys.exit(1)

    # Remove old symlink if present (migration from previous deploy method)
    if target.is_symlink():
        print(f"Removing old symlink: {target}")
        target.unlink()

    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(skill_src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Deployed to {target}")


if __name__ == "__main__":
    main()
