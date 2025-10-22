"""SQLite storage helpers for the personal project manager app."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH, ensure_directories

SCHEMA = """
-- Projects remain largely the same
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- NEW: Contacts (extracted from communication senders/recipients)
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- NEW: Communications (replaces emails, but more generic)
CREATE TABLE IF NOT EXISTS communications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL, -- 'email', 'whatsapp', 'messenger', 'sms', 'note', 'file', 'meeting'
    content TEXT, -- full body/message content
    subject TEXT, -- for emails, meeting titles, etc
    snippet TEXT, -- preview text
    timestamp TEXT, -- when the communication happened
    raw_path TEXT, -- path to .eml file, exported chat, etc
    source_id TEXT, -- external ID (Gmail message_id, WhatsApp msg id, etc)
    status TEXT NOT NULL DEFAULT 'unassigned', -- 'unassigned', 'assigned', 'snoozed', 'ignored'
    remind_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(type, source_id)
);

-- NEW: Many-to-many link between projects and communications
-- Includes the contact involved in this communication for this project
CREATE TABLE IF NOT EXISTS project_communications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    communication_id INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(communication_id) REFERENCES communications(id) ON DELETE CASCADE,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    UNIQUE(project_id, communication_id, contact_id)
);

-- NEW: Track which contacts are involved in which projects
CREATE TABLE IF NOT EXISTS project_contacts (
    project_id INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    role TEXT, -- 'lead', 'collaborator', 'client', etc (optional)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(project_id, contact_id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);

-- Keep ignored senders for now (can migrate to contact-based ignore later)
CREATE TABLE IF NOT EXISTS ignored_senders (
    email TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- LEGACY: Keep old emails table for backward compatibility during migration
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

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_communications_type ON communications(type);
CREATE INDEX IF NOT EXISTS idx_communications_status ON communications(status);
CREATE INDEX IF NOT EXISTS idx_communications_timestamp ON communications(timestamp);
CREATE INDEX IF NOT EXISTS idx_project_communications_project ON project_communications(project_id);
CREATE INDEX IF NOT EXISTS idx_project_communications_contact ON project_communications(contact_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
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
