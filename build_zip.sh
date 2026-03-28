#!/usr/bin/env bash
# Rebuild jetbriefcheck.zip from the skill/ directory.
# Usage: ./build_zip.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
TMP=$(mktemp -d)
DEST="$TMP/jetbriefcheck"

cp -r "$REPO_ROOT/skill" "$DEST"

# Clean build artifacts
find "$DEST" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name '*.pyc' -delete 2>/dev/null || true

# Build ZIP
(cd "$TMP" && zip -r "$REPO_ROOT/jetbriefcheck.zip" jetbriefcheck/)

rm -rf "$TMP"
echo "Built: $REPO_ROOT/jetbriefcheck.zip"
