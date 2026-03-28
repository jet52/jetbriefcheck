"""Pytest configuration — add skill/ to import path so tests can import core.*"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "skill"))
