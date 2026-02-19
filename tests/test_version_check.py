"""Tests for core.version_check module.

Covers:
- Loading local version.json
- Rule hash computation and integrity checking
- Rule staleness detection
- Remote version check (mocked, fail-open)
- Report footer version stamp
- Report HTML footer rendering
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is importable
import sys
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from core.version_check import (
    VERSION_FILE,
    RULES_DIR,
    check_remote_version,
    check_rule_hashes,
    check_rule_staleness,
    compute_all_rule_hashes,
    compute_rule_hash,
    fetch_remote_version,
    get_version_stamp,
    get_version_warnings,
    load_local_version,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def local_version():
    """Return the actual version.json content."""
    return load_local_version()


@pytest.fixture
def tmp_rule_file(tmp_path):
    """Create a temporary rule file with known content."""
    f = tmp_path / "rule-test.md"
    f.write_text("# Rule 99. Testing.\n\nThis is a test rule.\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# 1. Loading version.json
# ---------------------------------------------------------------------------

class TestLoadLocalVersion:
    def test_loads_successfully(self, local_version):
        assert isinstance(local_version, dict)
        assert "version" in local_version
        assert "rules_verified" in local_version
        assert "rule_hashes" in local_version

    def test_returns_expected_version(self, local_version):
        assert local_version["version"] == "1.1.0"

    def test_returns_empty_dict_for_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.version_check.VERSION_FILE", tmp_path / "nope.json")
        result = load_local_version()
        assert result == {}

    def test_returns_empty_dict_for_bad_json(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{", encoding="utf-8")
        monkeypatch.setattr("core.version_check.VERSION_FILE", bad)
        result = load_local_version()
        assert result == {}


# ---------------------------------------------------------------------------
# 2. Rule hash computation
# ---------------------------------------------------------------------------

class TestRuleHashes:
    def test_compute_single_hash(self, tmp_rule_file):
        h = compute_rule_hash(tmp_rule_file)
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64  # "sha256:" + 64 hex chars

    def test_hash_is_deterministic(self, tmp_rule_file):
        h1 = compute_rule_hash(tmp_rule_file)
        h2 = compute_rule_hash(tmp_rule_file)
        assert h1 == h2

    def test_hash_changes_with_content(self, tmp_rule_file):
        h1 = compute_rule_hash(tmp_rule_file)
        tmp_rule_file.write_text("different content\n", encoding="utf-8")
        h2 = compute_rule_hash(tmp_rule_file)
        assert h1 != h2

    def test_compute_all_hashes_finds_real_rules(self):
        hashes = compute_all_rule_hashes()
        assert len(hashes) >= 6
        expected_files = {"rule-28.md", "rule-29.md", "rule-30.md",
                          "rule-32.md", "rule-34.md", "rule-3.4.md"}
        assert expected_files.issubset(set(hashes.keys()))
        for h in hashes.values():
            assert h.startswith("sha256:")

    def test_computed_hashes_match_version_json(self, local_version):
        """The on-disk rule files should match the hashes stored in version.json."""
        actual = compute_all_rule_hashes()
        expected = local_version.get("rule_hashes", {})
        for filename, expected_hash in expected.items():
            assert filename in actual, f"Rule file {filename} not found on disk"
            assert actual[filename] == expected_hash, (
                f"Hash mismatch for {filename}: "
                f"version.json says {expected_hash}, disk says {actual[filename]}"
            )


# ---------------------------------------------------------------------------
# 3. Rule hash integrity checking
# ---------------------------------------------------------------------------

class TestCheckRuleHashes:
    def test_no_warnings_when_hashes_match(self, local_version):
        warnings = check_rule_hashes(local_version)
        assert warnings == []

    def test_warns_on_hash_mismatch(self, local_version):
        tampered = dict(local_version)
        tampered["rule_hashes"] = dict(tampered["rule_hashes"])
        tampered["rule_hashes"]["rule-28.md"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        warnings = check_rule_hashes(tampered)
        assert len(warnings) == 1
        assert "rule-28.md" in warnings[0]
        assert "modified" in warnings[0]

    def test_warns_on_missing_rule_file(self, local_version):
        tampered = dict(local_version)
        tampered["rule_hashes"] = dict(tampered["rule_hashes"])
        tampered["rule_hashes"]["rule-999.md"] = "sha256:abc123"
        warnings = check_rule_hashes(tampered)
        assert any("rule-999.md" in w for w in warnings)
        assert any("missing" in w.lower() for w in warnings)

    def test_no_warnings_when_no_hashes_in_version(self):
        warnings = check_rule_hashes({"version": "1.0.0"})
        assert warnings == []

    def test_no_warnings_for_empty_dict(self):
        warnings = check_rule_hashes({})
        assert warnings == []


# ---------------------------------------------------------------------------
# 4. Rule staleness detection
# ---------------------------------------------------------------------------

class TestCheckRuleStaleness:
    def test_no_warning_when_fresh(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        result = check_rule_staleness({
            "rules_verified": yesterday,
            "rules_freshness_days": 90,
        })
        assert result is None

    def test_no_warning_at_boundary(self):
        boundary = (date.today() - timedelta(days=90)).isoformat()
        result = check_rule_staleness({
            "rules_verified": boundary,
            "rules_freshness_days": 90,
        })
        assert result is None

    def test_warns_when_stale(self):
        old_date = (date.today() - timedelta(days=91)).isoformat()
        result = check_rule_staleness({
            "rules_verified": old_date,
            "rules_freshness_days": 90,
        })
        assert result is not None
        assert "91 days ago" in result
        assert "ndcourts.gov" in result

    def test_warns_when_very_stale(self):
        old_date = (date.today() - timedelta(days=365)).isoformat()
        result = check_rule_staleness({
            "rules_verified": old_date,
            "rules_freshness_days": 90,
        })
        assert result is not None
        assert "365 days ago" in result

    def test_custom_freshness_threshold(self):
        old_date = (date.today() - timedelta(days=31)).isoformat()
        result = check_rule_staleness({
            "rules_verified": old_date,
            "rules_freshness_days": 30,
        })
        assert result is not None

    def test_no_warning_when_missing_date(self):
        assert check_rule_staleness({}) is None
        assert check_rule_staleness({"rules_verified": ""}) is None

    def test_no_warning_for_invalid_date(self):
        assert check_rule_staleness({"rules_verified": "not-a-date"}) is None

    def test_defaults_to_90_days_if_threshold_missing(self):
        fresh = (date.today() - timedelta(days=89)).isoformat()
        assert check_rule_staleness({"rules_verified": fresh}) is None
        stale = (date.today() - timedelta(days=91)).isoformat()
        assert check_rule_staleness({"rules_verified": stale}) is not None


# ---------------------------------------------------------------------------
# 5. Remote version check (mocked)
# ---------------------------------------------------------------------------

class TestRemoteVersionCheck:
    def test_fetch_returns_none_on_network_error(self):
        """Remote fetch should fail open — return None, not raise."""
        with patch("core.version_check.load_local_version", return_value={
            "check_url": "http://192.0.2.1/version.json"  # RFC 5737 TEST-NET
        }):
            result = fetch_remote_version(timeout=0.5)
            assert result is None

    def test_fetch_returns_none_when_no_url(self):
        with patch("core.version_check.load_local_version", return_value={}):
            result = fetch_remote_version()
            assert result is None

    def test_check_remote_no_messages_when_fetch_fails(self, local_version):
        with patch("core.version_check.fetch_remote_version", return_value=None):
            messages = check_remote_version(local_version)
            assert messages == []

    def test_check_remote_no_messages_when_versions_match(self, local_version):
        with patch("core.version_check.fetch_remote_version", return_value=local_version):
            messages = check_remote_version(local_version)
            assert messages == []

    def test_check_remote_warns_on_newer_version(self, local_version):
        remote = dict(local_version)
        remote["version"] = "2.0.0"
        with patch("core.version_check.fetch_remote_version", return_value=remote):
            messages = check_remote_version(local_version)
            assert len(messages) >= 1
            assert "2.0.0" in messages[0]
            assert "v1.1.0" in messages[0]

    def test_check_remote_warns_on_newer_rules(self, local_version):
        remote = dict(local_version)
        remote["rules_verified"] = "2099-01-01"
        with patch("core.version_check.fetch_remote_version", return_value=remote):
            messages = check_remote_version(local_version)
            assert any("2099-01-01" in m for m in messages)


# ---------------------------------------------------------------------------
# 6. get_version_warnings (integration)
# ---------------------------------------------------------------------------

class TestGetVersionWarnings:
    def test_clean_run_no_warnings(self):
        """With current files in good shape, no warnings expected (skip remote)."""
        warnings = get_version_warnings(check_remote=False)
        assert warnings == []

    def test_remote_disabled_skips_fetch(self):
        with patch("core.version_check.check_remote_version") as mock_remote:
            get_version_warnings(check_remote=False)
            mock_remote.assert_not_called()

    def test_remote_enabled_calls_fetch(self):
        with patch("core.version_check.check_remote_version", return_value=[]) as mock_remote:
            get_version_warnings(check_remote=True, timeout=0.1)
            mock_remote.assert_called_once()

    def test_aggregates_all_warning_types(self):
        """Simulate hash mismatch + staleness simultaneously."""
        fake_version = {
            "version": "1.1.0",
            "rules_verified": "2020-01-01",
            "rules_freshness_days": 90,
            "rule_hashes": {
                "rule-28.md": "sha256:0000",
            },
        }
        with patch("core.version_check.load_local_version", return_value=fake_version):
            warnings = get_version_warnings(check_remote=False)
            assert len(warnings) >= 2
            has_hash_warning = any("modified" in w or "mismatch" in w for w in warnings)
            has_stale_warning = any("ndcourts.gov" in w for w in warnings)
            assert has_hash_warning
            assert has_stale_warning


# ---------------------------------------------------------------------------
# 7. Version stamp for report footer
# ---------------------------------------------------------------------------

class TestGetVersionStamp:
    def test_returns_expected_format(self):
        stamp = get_version_stamp()
        assert "v1.1.0" in stamp
        assert "Rules verified 2026-02-17" in stamp
        assert "|" in stamp

    def test_returns_empty_for_missing_version_file(self, monkeypatch):
        monkeypatch.setattr("core.version_check.VERSION_FILE", Path("/nonexistent/version.json"))
        stamp = get_version_stamp()
        assert stamp == ""


# ---------------------------------------------------------------------------
# 8. Report footer rendering
# ---------------------------------------------------------------------------

class TestReportFooter:
    def test_footer_contains_version_stamp(self):
        from core.models import ComplianceReport, BriefType, Recommendation
        from core.report_builder import build_html_report

        report = ComplianceReport(
            brief_type=BriefType.APPELLANT,
            recommendation=Recommendation.ACCEPT,
            results=[],
            report_id="test123",
        )
        html = build_html_report(report, version_stamp="v1.1.0 | Rules verified 2026-02-17")
        assert "v1.1.0" in html
        assert "Rules verified 2026-02-17" in html
        assert "&middot;" in html

    def test_footer_omits_stamp_when_empty(self):
        from core.models import ComplianceReport, BriefType, Recommendation
        from core.report_builder import build_html_report

        report = ComplianceReport(
            brief_type=BriefType.APPELLANT,
            recommendation=Recommendation.ACCEPT,
            results=[],
            report_id="test456",
        )
        html = build_html_report(report, version_stamp="")
        assert "&middot;" not in html
        assert "Brief Compliance Checker</p>" in html
