"""Core application logic for the personal project manager app."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Iterable, Optional

from . import database
from .config import RAW_EMAIL_DIR
from .email_utils import ParsedEmail, parse_email_file, parse_raw_email


@dataclass
class Project:
    id: int
    name: str


@dataclass
class EmailEntry:
    id: int
    message_id: str
    subject: Optional[str]
    sender: Optional[str]
    received_at: Optional[str]
    snippet: str
    status: str
    project_id: Optional[int]
    remind_at: Optional[str]


def _row_to_email(row) -> EmailEntry:
    """Convert a database row to an :class:`EmailEntry`."""

    return EmailEntry(
        id=row["id"],
        message_id=row["message_id"],
        subject=row["subject"],
        sender=row["sender"],
        received_at=row["received_at"],
        snippet=row["snippet"],
        status=row["status"],
        project_id=row["project_id"],
        remind_at=row["remind_at"],
    )


class ProjectManager:
    """High level application service coordinating storage and prompts."""

    def __init__(self) -> None:
        database.initialize()

    # Project helpers ------------------------------------------------------------------
    def list_projects(self) -> list[Project]:
        with database.db_session() as conn:
            rows = conn.execute("SELECT id, name FROM projects ORDER BY created_at").fetchall()
            return [Project(id=row["id"], name=row["name"]) for row in rows]

    def create_project(self, name: str) -> Project:
        with database.db_session() as conn:
            cur = conn.execute("INSERT INTO projects(name) VALUES (?)", (name.strip(),))
            project_id = cur.lastrowid
            row = conn.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
            return Project(id=row["id"], name=row["name"])

    # Sender preferences ---------------------------------------------------------------
    def is_sender_ignored(self, sender: Optional[str]) -> bool:
        if not sender:
            return False
        with database.db_session() as conn:
            row = conn.execute(
                "SELECT 1 FROM ignored_senders WHERE email = ?", (sender.strip(),)
            ).fetchone()
            return row is not None

    def ignore_sender(self, sender: str) -> None:
        with database.db_session() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ignored_senders(email) VALUES (?)", (sender.strip(),)
            )

    # Email helpers --------------------------------------------------------------------
    def upsert_email(self, parsed: ParsedEmail, raw_storage_path: Path) -> EmailEntry:
        with database.db_session() as conn:
            conn.execute(
                """
                INSERT INTO emails(message_id, subject, sender, received_at, snippet, raw_path)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    subject = excluded.subject,
                    sender = excluded.sender,
                    received_at = excluded.received_at,
                    snippet = excluded.snippet,
                    raw_path = excluded.raw_path,
                    updated_at = datetime('now')
                """,
                (
                    parsed.message_id,
                    parsed.subject,
                    parsed.sender,
                    parsed.received_at,
                    parsed.snippet,
                    str(raw_storage_path),
                ),
            )
            row = conn.execute(
                "SELECT * FROM emails WHERE message_id = ?", (parsed.message_id,)
            ).fetchone()
            return _row_to_email(row)

    def set_email_project(self, email_id: int, project_id: int) -> None:
        with database.db_session() as conn:
            conn.execute(
                """
                UPDATE emails
                SET project_id = ?, status = 'assigned', remind_at = NULL, updated_at = datetime('now')
                WHERE id = ?
                """,
                (project_id, email_id),
            )

    def set_email_snooze(self, email_id: int, remind_at: datetime) -> None:
        with database.db_session() as conn:
            conn.execute(
                """
                UPDATE emails
                SET status = 'snoozed', remind_at = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (remind_at.isoformat(timespec="seconds"), email_id),
            )

    def set_email_ignored(self, email_id: int) -> None:
        with database.db_session() as conn:
            conn.execute(
                """
                UPDATE emails
                SET status = 'ignored', updated_at = datetime('now')
                WHERE id = ?
                """,
                (email_id,),
            )

    def get_email(self, email_id: int) -> Optional[EmailEntry]:
        with database.db_session() as conn:
            row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        if row is None:
            return None
        return _row_to_email(row)

    def list_pending_reminders(self) -> list[EmailEntry]:
        with database.db_session() as conn:
            rows = conn.execute(
                """
SELECT * FROM emails
WHERE status = 'snoozed'
  AND remind_at IS NOT NULL
  AND datetime(remind_at) <= datetime('now')
ORDER BY datetime(remind_at)
                """
            ).fetchall()
        return [_row_to_email(row) for row in rows]

    # High level flow ------------------------------------------------------------------
    def ingest_email_file(self, path: Path) -> Optional[EmailEntry]:
        parsed = parse_email_file(path)
        if self.is_sender_ignored(parsed.sender):
            return None

        safe_stem = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in parsed.message_id
        )
        storage_path = RAW_EMAIL_DIR / f"{safe_stem}.eml"
        shutil.copy2(path, storage_path)

        return self.upsert_email(parsed, storage_path)

    def ingest_from_source(self, raw_email) -> Optional[EmailEntry]:
        """Ingest an email from an email source (Gmail, Apple Mail, etc.)."""
        # Import here to avoid circular dependency
        from .email_sources import RawEmail

        if self.is_sender_ignored(raw_email.sender):
            return None

        # Create safe filename from message_id
        safe_stem = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw_email.message_id
        )
        storage_path = RAW_EMAIL_DIR / f"{safe_stem}.eml"

        # Save raw email content to storage
        storage_path.write_bytes(raw_email.raw_content)

        # Parse to our internal format
        parsed = parse_raw_email(raw_email, storage_path)

        return self.upsert_email(parsed, storage_path)

    def fetch_from_all_sources(self, max_per_source: int = 10) -> list[EmailEntry]:
        """Fetch emails from all configured email sources."""
        from .email_sources import get_available_sources

        sources = get_available_sources()
        ingested_emails = []

        for source in sources:
            try:
                raw_emails = source.fetch_unread(max_results=max_per_source)
                print(f"Fetched {len(raw_emails)} emails from {source.__class__.__name__}")

                for raw_email in raw_emails:
                    email_entry = self.ingest_from_source(raw_email)
                    if email_entry:
                        ingested_emails.append(email_entry)
                        # Optionally mark as processed in the source
                        # source.mark_as_processed(raw_email.source_id)

            except Exception as e:
                print(f"Error fetching from {source.__class__.__name__}: {e}")
                continue

        return ingested_emails


REMINDER_OFFSETS = {
    "1": ("in 1 day", timedelta(days=1)),
    "2": ("in 1 week", timedelta(weeks=1)),
    "3": ("in 1 month", timedelta(days=30)),
}


def prompt_user_for_email(manager: ProjectManager, email: EmailEntry) -> None:
    """Interactive prompt for categorising an email."""
    print("\nNew email detected:")
    print(f"From: {email.sender or 'Unknown'}")
    print(f"Subject: {email.subject or '(no subject)'}")
    print(f"Received: {email.received_at or 'Unknown'}")
    if email.snippet:
        print(f"Snippet: {email.snippet}")

    projects = manager.list_projects()
    if projects:
        print("\nAssign to an existing project:")
        for index, project in enumerate(projects, start=1):
            print(f"  [{index}] {project.name}")
    else:
        print("\nNo projects yet. You can create a new one.")

    extra_offset = len(projects)
    create_option = extra_offset + 1
    snooze_option = extra_offset + 2
    ignore_option = extra_offset + 3

    print(f"  [{create_option}] Create a new project")
    print(f"  [{snooze_option}] Decide later (snooze)")
    print(f"  [{ignore_option}] Never ask for emails from this sender")

    while True:
        choice = input("Select an option: ").strip()
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(projects):
                selected_project = projects[number - 1]
                manager.set_email_project(email.id, selected_project.id)
                print(f"Assigned to project: {selected_project.name}")
                return
            if number == create_option:
                name = input("New project name: ").strip()
                if not name:
                    print("Project name cannot be empty.")
                    continue
                project = manager.create_project(name)
                manager.set_email_project(email.id, project.id)
                print(f"Created and assigned to project: {project.name}")
                return
            if number == snooze_option:
                _handle_snooze(manager, email)
                return
            if number == ignore_option:
                if email.sender:
                    manager.ignore_sender(email.sender)
                manager.set_email_ignored(email.id)
                print("Sender ignored for future emails.")
                return
        print("Invalid choice. Please select a listed option.")


def _handle_snooze(manager: ProjectManager, email: EmailEntry) -> None:
    print("\nSnooze options:")
    for key, (label, _) in REMINDER_OFFSETS.items():
        print(f"  [{key}] Remind me {label}")
    while True:
        choice = input("Select reminder interval: ").strip()
        if choice in REMINDER_OFFSETS:
            label, delta = REMINDER_OFFSETS[choice]
            remind_at = datetime.now(UTC) + delta

            manager.set_email_snooze(email.id, remind_at)
            print(f"Email snoozed until {remind_at.isoformat(timespec='seconds')} ({label}).")
            return
        print("Invalid choice. Try again.")


def iter_pending_emails(manager: ProjectManager, statuses: Iterable[str] = ("unassigned", "snoozed")) -> list[EmailEntry]:
    placeholders = ",".join("?" for _ in statuses)
    query = (
        "SELECT * FROM emails WHERE status IN (%s) ORDER BY updated_at" % placeholders
    )
    with database.db_session() as conn:
        rows = conn.execute(query, tuple(statuses)).fetchall()
    return [_row_to_email(row) for row in rows]
