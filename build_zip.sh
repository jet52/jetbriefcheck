#!/usr/bin/env bash
# Rebuild jetbriefcheck.zip from the current source files.
# Usage: ./build_zip.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
TMP=$(mktemp -d)
DEST="$TMP/jetbriefcheck"

mkdir -p "$DEST"

cp -r "$REPO_ROOT/core"       "$DEST/core"
cp -r "$REPO_ROOT/references" "$DEST/references"
cp -r "$REPO_ROOT/scripts"    "$DEST/scripts"
cp    "$REPO_ROOT/SKILL.md"          "$DEST/SKILL.md"
cp    "$REPO_ROOT/requirements.txt"  "$DEST/requirements.txt"
cp    "$REPO_ROOT/version.json"      "$DEST/version.json"
cp    "$REPO_ROOT/check_update.py"    "$DEST/check_update.py"

# Clean build artifacts
find "$DEST" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name '*.pyc' -delete 2>/dev/null || true

# Build ZIP
(cd "$TMP" && zip -r "$REPO_ROOT/jetbriefcheck.zip" jetbriefcheck/)

rm -rf "$TMP"
echo "Built: $REPO_ROOT/jetbriefcheck.zip"
