#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="jetbriefcheck"
INSTALL_DIR="$HOME/.claude/skills/$SKILL_NAME"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing $SKILL_NAME skill..."

# Create target directory
mkdir -p "$INSTALL_DIR"

# Copy skill files
ITEMS=(SKILL.md scripts references core requirements.txt version.json)
for item in "${ITEMS[@]}"; do
    src="$SCRIPT_DIR/$item"
    if [ -e "$src" ]; then
        rm -rf "$INSTALL_DIR/$item"
        cp -a "$src" "$INSTALL_DIR/$item"
        echo "  Copied: $item"
    fi
done

echo "Installed to $INSTALL_DIR"

# --- Python virtual environment ---
echo ""
echo "Setting up Python virtual environment..."

VENV_DIR="$INSTALL_DIR/.venv"

if command -v uv &>/dev/null; then
    echo "Using uv to create venv..."
    uv venv "$VENV_DIR" --clear
    uv pip install -r "$INSTALL_DIR/requirements.txt" --python "$VENV_DIR/bin/python"
elif command -v python3 &>/dev/null; then
    echo "Using python3 to create venv..."
    python3 -m venv "$VENV_DIR" --clear
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
else
    echo "ERROR: Neither uv nor python3 found. Cannot create virtual environment."
    echo "  Install Python 3 from https://www.python.org/ or uv from https://docs.astral.sh/uv/"
    exit 1
fi

echo "Python packages installed."
echo ""
echo "Done."
