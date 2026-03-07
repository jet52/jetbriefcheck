#!/usr/bin/env python3
"""Check bundled rule freshness against ndcourts.gov effective dates.

Fetches each rule's page, extracts the current effective date, and compares
against the bundled effective dates. Bypasses the cache to always check live.

Uses the same data and logic as core.version_check but forces a live check.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from core.version_check import (
    BUNDLED_EFFECTIVE_DATES,
    RULE_URLS,
    _check_rules_live,
    _fetch_effective_date,
    load_local_version,
)


def main() -> int:
    version_data = load_local_version()
    rules_verified = version_data.get("rules_verified", "unknown")

    print(f"Bundled rules last verified: {rules_verified}")
    print(f"Checking {len(RULE_URLS)} rules against ndcourts.gov...\n")

    stale = []
    errors = []

    for rule, url in sorted(RULE_URLS.items()):
        bundled_date = BUNDLED_EFFECTIVE_DATES.get(rule, "unknown")
        print(f"  {rule:12s}  bundled effective: {bundled_date}  ", end="", flush=True)

        live_date = _fetch_effective_date(url)

        if live_date is None:
            errors.append(rule)
            print("-> FETCH ERROR")
        elif live_date != bundled_date:
            stale.append((rule, bundled_date, live_date))
            print(f"-> STALE (live: {live_date})")
        else:
            print("-> current")

    print()

    if errors:
        print(f"Could not check {len(errors)} rule(s): {', '.join(errors)}")

    if stale:
        print(f"{len(stale)} rule(s) may need updating:")
        for rule, bundled, live in stale:
            print(f"  {rule}: bundled {bundled}, ndcourts.gov shows {live}")
            print(f"    URL: {RULE_URLS[rule]}")
        return 1
    elif not errors:
        print("All rules are current.")

    # Also update the cache since we just did a live check
    print("\nUpdating staleness cache...")
    _check_rules_live()
    print("Cache updated.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
