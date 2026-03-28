"""Version and rule freshness checking for the brief compliance skill.

Provides:
- Local version info reading
- Remote version check (lightweight, fail-open)
- Rule content hash verification
- Rule staleness check against ndcourts.gov (cached, 90-day refresh)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

PROJECT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_DIR / "version.json"
RULES_DIR = PROJECT_DIR / "references" / "rules"
STALENESS_CACHE = Path.home() / ".cache" / "jetbriefcheck" / "rule_staleness.json"
STALENESS_MAX_AGE_DAYS = 90

# Map rule file stems to ndcourts.gov URLs
RULE_URLS = {
    "rule-14": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/14",
    "rule-21": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/21",
    "rule-28": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/28",
    "rule-29": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/29",
    "rule-30": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/30",
    "rule-32": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/32",
    "rule-34": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/34",
    "rule-3.4": "https://www.ndcourts.gov/legal-resources/rules/ndrct/3-4",
    "rule-11.6": "https://www.ndcourts.gov/legal-resources/rules/ndrct/11-6",
}

# Effective dates at the time rules were last bundled (update when rules are refreshed)
BUNDLED_EFFECTIVE_DATES = {
    "rule-14": "2020-03-01",
    "rule-21": "2022-03-01",
    "rule-28": "2025-06-01",
    "rule-29": "2022-03-01",
    "rule-30": "2023-01-25",
    "rule-32": "2024-04-01",
    "rule-34": "2025-09-01",
    "rule-3.4": "2025-03-01",
    "rule-11.6": "2025-03-01",
}

EFFECTIVE_DATE_RE = re.compile(r"Effective\s+Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})")


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


def _load_staleness_cache() -> dict:
    """Load the cached staleness result. Returns empty dict if missing/corrupt."""
    try:
        return json.loads(STALENESS_CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_staleness_cache(data: dict) -> None:
    """Write staleness cache, creating parent dirs as needed."""
    try:
        STALENESS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        STALENESS_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # fail silently — cache is advisory


def _fetch_effective_date(url: str, timeout: float = 10.0) -> Optional[str]:
    """Fetch a rule page on ndcourts.gov and extract the effective date as YYYY-MM-DD."""
    try:
        req = Request(url, headers={"User-Agent": "jetbriefcheck-freshness-check"})
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    match = EFFECTIVE_DATE_RE.search(html)
    if not match:
        return None

    try:
        dt = datetime.strptime(match.group(1), "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _check_rules_live() -> list[str]:
    """Fetch effective dates from ndcourts.gov and compare against bundled dates.

    Returns a list of warning strings for any stale rules. Saves results to cache.
    """
    stale = []
    live_dates = {}

    for rule, url in RULE_URLS.items():
        bundled = BUNDLED_EFFECTIVE_DATES.get(rule)
        if not bundled:
            continue
        live = _fetch_effective_date(url)
        if live:
            live_dates[rule] = live
            if live != bundled:
                stale.append(
                    f"Rule {rule} may be outdated: bundled effective date "
                    f"{bundled}, ndcourts.gov shows {live}. "
                    f"Check {url}"
                )

    _save_staleness_cache({
        "last_checked": date.today().isoformat(),
        "live_dates": live_dates,
        "stale_rules": [s.split(":")[0].replace("Rule ", "") for s in stale],
        "warnings": stale,
    })

    return stale


def check_rule_staleness(local_version: dict) -> list[str]:
    """Check bundled rules against ndcourts.gov effective dates (cached).

    Uses a local cache at ~/.cache/jetbriefcheck/rule_staleness.json.
    Re-checks live every 90 days. Returns a list of warning strings.
    """
    cache = _load_staleness_cache()
    last_checked_str = cache.get("last_checked")

    if last_checked_str:
        try:
            last_checked = datetime.strptime(last_checked_str, "%Y-%m-%d").date()
            age = (date.today() - last_checked).days
            if age < STALENESS_MAX_AGE_DAYS:
                return cache.get("warnings", [])
        except ValueError:
            pass

    # Cache is missing, expired, or corrupt — check live (fail-open)
    try:
        return _check_rules_live()
    except Exception:
        return []


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
        req = Request(url, headers={"User-Agent": "jetbriefcheck"})
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
            f"Visit https://github.com/jet52/jetbriefcheck for updates."
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

    # Rule staleness check (cached, checks ndcourts.gov every 90 days)
    warnings.extend(check_rule_staleness(local))

    # Remote version check (fail-open)
    if check_remote:
        warnings.extend(check_remote_version(local, timeout=timeout))

    return warnings


def get_version_stamp() -> str:
    """Return a short version + build date + rule date string for report footers.

    Example: "v1.6.0 (2026-02-25) · Rules current as of 2026-02-17"
    """
    local = load_local_version()
    if not local:
        return ""

    version = local.get("version", "")
    build_date = local.get("build_date", "")
    verified = local.get("rules_verified", "")

    if not version:
        return ""

    stamp = f"v{version}"
    if build_date:
        stamp += f" ({build_date})"
    if verified:
        stamp += f" · Rules current as of {verified}"

    return stamp
