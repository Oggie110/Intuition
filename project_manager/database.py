"""SQLite storage helpers for the personal project manager app."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH, ensure_directories

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ignored_senders (
    email TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    subject TEXT,
    sender TEXT,
    received_at TEXT,
    snippet TEXT,
    raw_path TEXT,
    project_id INTEGER,
    status TEXT NOT NULL DEFAULT 'unassigned',
    remind_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
"""


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection with sensible defaults."""
    ensure_directories()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def initialize() -> None:
    """Ensure the database schema is present."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    """Context manager yielding a database connection."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
