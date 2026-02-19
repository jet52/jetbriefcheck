"""Version and rule freshness checking for the brief compliance skill.

Provides:
- Local version info reading
- Remote version check (lightweight, fail-open)
- Rule content hash verification
- Rule staleness warning based on age since last verification
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_DIR / "version.json"
RULES_DIR = PROJECT_DIR / "references" / "rules"


def load_local_version() -> dict:
    """Load the local version.json. Returns empty dict on failure."""
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def compute_rule_hash(rule_file: Path) -> str:
    """Compute SHA-256 hash of a rule file, prefixed with 'sha256:'."""
    content = rule_file.read_bytes()
    return "sha256:" + hashlib.sha256(content).hexdigest()


def compute_all_rule_hashes() -> dict[str, str]:
    """Compute hashes for all rule files in the rules directory."""
    hashes = {}
    if RULES_DIR.is_dir():
        for f in sorted(RULES_DIR.glob("*.md")):
            hashes[f.name] = compute_rule_hash(f)
    return hashes


def check_rule_hashes(local_version: dict) -> list[str]:
    """Compare on-disk rule hashes against those in version.json.

    Returns a list of warning strings for any mismatches.
    """
    expected = local_version.get("rule_hashes", {})
    if not expected:
        return []

    warnings = []
    actual = compute_all_rule_hashes()

    for filename, expected_hash in expected.items():
        actual_hash = actual.get(filename)
        if actual_hash is None:
            warnings.append(f"Rule file missing: {filename}")
        elif actual_hash != expected_hash:
            warnings.append(
                f"Rule file {filename} has been modified since last release "
                f"(hash mismatch)"
            )

    return warnings


def check_rule_staleness(local_version: dict) -> Optional[str]:
    """Check if rules are older than the configured freshness threshold.

    Returns a warning string if stale, None otherwise.
    """
    verified_str = local_version.get("rules_verified")
    if not verified_str:
        return None

    try:
        verified_date = datetime.strptime(verified_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    max_days = local_version.get("rules_freshness_days", 90)
    age_days = (date.today() - verified_date).days

    if age_days > max_days:
        return (
            f"Bundled rules were last verified {age_days} days ago "
            f"({verified_str}). Consider checking ndcourts.gov for amendments "
            f"to Rules 28, 29, 30, 32, 34, and 3.4."
        )
    return None


def fetch_remote_version(timeout: float = 2.0) -> Optional[dict]:
    """Fetch the remote version.json from the check_url.

    Returns the parsed JSON dict, or None on any failure.
    Uses a short timeout and fails open (returns None) on error.
    """
    local = load_local_version()
    url = local.get("check_url")
    if not url:
        return None

    try:
        from urllib.request import urlopen, Request
        req = Request(url, headers={"User-Agent": "brief-compliance-skill"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_remote_version(local_version: dict, timeout: float = 2.0) -> list[str]:
    """Compare local version against remote. Returns advisory messages."""
    remote = fetch_remote_version(timeout=timeout)
    if remote is None:
        return []

    messages = []
    local_ver = local_version.get("version", "0.0.0")
    remote_ver = remote.get("version", "0.0.0")

    if remote_ver != local_ver:
        messages.append(
            f"A newer version of the brief compliance skill is available: "
            f"v{remote_ver} (you have v{local_ver}). "
            f"Visit https://github.com/jet52/ndsc-brief-compliance for updates."
        )

    # Check if remote has newer rule hashes (rules updated upstream)
    remote_verified = remote.get("rules_verified", "")
    local_verified = local_version.get("rules_verified", "")
    if remote_verified > local_verified:
        messages.append(
            f"Updated rules are available (verified {remote_verified}, "
            f"yours verified {local_verified}). Consider updating."
        )

    return messages


def get_version_warnings(check_remote: bool = True, timeout: float = 2.0) -> list[str]:
    """Main entry point: collect all version/freshness warnings.

    Args:
        check_remote: Whether to attempt a remote version check.
        timeout: Timeout in seconds for the remote check.

    Returns:
        List of warning strings (may be empty).
    """
    local = load_local_version()
    if not local:
        return []

    warnings = []

    # Rule hash integrity check
    warnings.extend(check_rule_hashes(local))

    # Rule staleness check
    staleness = check_rule_staleness(local)
    if staleness:
        warnings.append(staleness)

    # Remote version check (fail-open)
    if check_remote:
        warnings.extend(check_remote_version(local, timeout=timeout))

    return warnings


def get_version_stamp() -> str:
    """Return a short version + rule date string for report footers.

    Example: "v1.1.0 | Rules verified 2026-02-17"
    """
    local = load_local_version()
    if not local:
        return ""

    parts = []
    version = local.get("version")
    if version:
        parts.append(f"v{version}")

    verified = local.get("rules_verified")
    if verified:
        parts.append(f"Rules verified {verified}")

    return " | ".join(parts)
