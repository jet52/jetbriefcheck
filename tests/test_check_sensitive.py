"""Tests for scripts/check-sensitive.sh, the pre-push sensitive-content check.

Every new branch and tag once went unscanned: the hook built the new-ref range
as the single word "<sha> --not --remotes", git log rejected it, the error was
discarded, and an empty diff passed. Only pushes to a branch that already
existed on the remote were checked. The v2.7.0 tag reached the remote this
way while the same commits were blocked on main.

Each test builds a throwaway repository with a bare remote and feeds the hook
the pre-push lines git would send.

The docket is fabricated and cannot be real — county code 99 is outside ND's
01–53 — and is assembled at runtime so this file never trips the hook itself.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
HOOK = PROJECT_DIR / "scripts" / "check-sensitive.sh"
ZERO = "0" * 40
FAKE_DOCKET = "-".join(["99", "2019", "CV", "99999"])

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "remote.git")], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "test")
    _git(work, "config", "commit.gpgsign", "false")
    _git(work, "config", "tag.gpgsign", "false")
    (work / "a.txt").write_text("clean\n")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-qm", "init")
    _git(work, "remote", "add", "origin", "../remote.git")
    _git(work, "push", "-q", "--no-verify", "origin", "HEAD:main")
    return work


def _commit(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


def _hook(repo: Path, local_ref: str, local_sha: str, remote_sha: str = ZERO):
    line = f"{local_ref} {local_sha} {local_ref} {remote_sha}\n"
    return subprocess.run(["bash", str(HOOK)], cwd=repo, input=line,
                          capture_output=True, text=True)


def test_new_tag_is_scanned(repo):
    _commit(repo, "b.txt", f"see {FAKE_DOCKET}\n")
    _git(repo, "tag", "-a", "v9", "-m", "v9")
    r = _hook(repo, "refs/tags/v9", _git(repo, "rev-parse", "v9"))
    assert r.returncode == 1
    assert FAKE_DOCKET in r.stdout


def test_new_lightweight_tag_is_scanned(repo):
    sha = _commit(repo, "b.txt", f"see {FAKE_DOCKET}\n")
    _git(repo, "tag", "v9")
    r = _hook(repo, "refs/tags/v9", sha)
    assert r.returncode == 1


def test_new_branch_is_scanned(repo):
    sha = _commit(repo, "b.txt", f"see {FAKE_DOCKET}\n")
    r = _hook(repo, "refs/heads/feature", sha)
    assert r.returncode == 1
    assert FAKE_DOCKET in r.stdout


def test_existing_branch_is_scanned(repo):
    base = _git(repo, "rev-parse", "origin/main")
    sha = _commit(repo, "b.txt", f"see {FAKE_DOCKET}\n")
    r = _hook(repo, "refs/heads/main", sha, base)
    assert r.returncode == 1


def test_new_branch_binary_is_caught(repo):
    sha = _commit(repo, "brief.pdf", "%PDF-1.4\n")
    r = _hook(repo, "refs/heads/feature", sha)
    assert r.returncode == 1
    assert "brief.pdf" in r.stdout


def test_clean_new_tag_passes(repo):
    _commit(repo, "b.txt", "nothing sensitive\n")
    _git(repo, "tag", "-a", "v9", "-m", "v9")
    r = _hook(repo, "refs/tags/v9", _git(repo, "rev-parse", "v9"))
    assert r.returncode == 0, r.stdout


def test_tag_of_already_pushed_commit_passes(repo):
    """Commits already on the remote were checked when they were pushed."""
    base = _git(repo, "rev-parse", "origin/main")
    _git(repo, "tag", "-a", "v1", "-m", "v1", base)
    r = _hook(repo, "refs/tags/v1", _git(repo, "rev-parse", "v1"))
    assert r.returncode == 0, r.stdout


def test_allowlist_applies_to_new_refs(repo):
    (repo / ".sensitive-check-allow").write_text(FAKE_DOCKET + "\n")
    sha = _commit(repo, "b.txt", f"see {FAKE_DOCKET}\n")
    r = _hook(repo, "refs/heads/feature", sha)
    assert r.returncode == 0, r.stdout


def test_unreadable_range_fails_closed(repo):
    """A range git cannot resolve must block the push, not pass it."""
    sha = _commit(repo, "b.txt", "nothing sensitive\n")
    r = _hook(repo, "refs/heads/main", sha, "1" * 40)
    assert r.returncode == 1
    assert "could not read" in r.stdout


def test_branch_deletion_is_ignored(repo):
    r = _hook(repo, "refs/heads/old", ZERO, _git(repo, "rev-parse", "origin/main"))
    assert r.returncode == 0
