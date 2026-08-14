#!/usr/bin/env bash
# Deprecated shim. Packaging lives in the Makefile so there is one build path
# and no chance of the two drifting.
#
#   make package        # plugin zip only (the primary artifact)
#   make package-all    # plugin zip + standalone skill zip
#
# Kept because muscle memory and older notes still reach for this script.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "build_zip.sh is deprecated; running 'make package-all' instead." >&2
exec make -C "$REPO_ROOT" package-all
