"""Configuration for the appellate brief compliance checker."""

import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

UPLOAD_FOLDER = os.environ.get(
    "UPLOAD_FOLDER", os.path.join(tempfile.gettempdir(), "jetbriefcheck-uploads")
)
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-in-production")
