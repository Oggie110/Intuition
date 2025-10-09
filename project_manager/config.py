"""Configuration helpers for the personal project manager app."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "project_manager"


def get_home() -> Path:
    """Return the directory where the app stores persistent data."""
    env_path = os.environ.get("PROJECT_MANAGER_HOME")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path.home() / f".{APP_NAME}"


def ensure_directories() -> Path:
    """Ensure the storage directories exist and return the home path."""
    home = get_home()
    raw_email_dir = home / "raw_emails"
    raw_email_dir.mkdir(parents=True, exist_ok=True)
    return home


HOME_DIR = ensure_directories()
DB_PATH = HOME_DIR / "project_manager.db"
RAW_EMAIL_DIR = HOME_DIR / "raw_emails"
