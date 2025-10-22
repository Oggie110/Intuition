"""Core application logic for the personal project manager app."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from email.utils import parseaddr
from pathlib import Path
from typing import Iterable, Optional

from . import database
from .config import RAW_EMAIL_DIR
from .email_utils import ParsedEmail, parse_email_file, parse_raw_email


@dataclass
class Project:
    id: int
    name: str
    description: Optional[str] = None


@dataclass
class Contact:
    id: int
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    notes: Optional[str] = None


@dataclass
class Communication:
    id: int
    type: str  # 'email', 'whatsapp', 'messenger', 'sms', 'note', 'file', 'meeting'
    subject: Optional[str]
    snippet: Optional[str]
    timestamp: Optional[str]
    status: str
    remind_at: Optional[str]
    raw_path: Optional[str] = None
    # For backward compatibility with EmailEntry
    content: Optional[str] = None
    source_id: Optional[str] = None


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
    raw_path: Optional[str] = None


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
        raw_path=row["raw_path"] if "raw_path" in row.keys() else None,
    )


def _row_to_contact(row) -> Contact:
    """Convert a database row to a :class:`Contact`."""
    return Contact(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        notes=row["notes"] if "notes" in row.keys() else None,
    )


def _row_to_communication(row) -> Communication:
    """Convert a database row to a :class:`Communication`."""
    return Communication(
        id=row["id"],
        type=row["type"],
        subject=row["subject"],
        snippet=row["snippet"],
        timestamp=row["timestamp"],
        status=row["status"],
        remind_at=row["remind_at"],
        raw_path=row["raw_path"] if "raw_path" in row.keys() else None,
        content=row["content"] if "content" in row.keys() else None,
        source_id=row["source_id"] if "source_id" in row.keys() else None,
    )


def extract_contact_info(sender: str | None) -> tuple[str | None, str | None]:
    """Extract name and email from sender string.

    Examples:
        'John Doe <john@example.com>' -> ('John Doe', 'john@example.com')
        'john@example.com' -> (None, 'john@example.com')
    """
    if not sender:
        return None, None

    name, email = parseaddr(sender)

    # Clean up name
    if name:
        name = name.strip().strip('"').strip("'").strip()
        if not name:
            name = None

    # Clean up email
    if email:
        email = email.strip().lower()
        if not email:
            email = None

    return name, email


class ProjectManager:
    """High level application service coordinating storage and prompts."""

    def __init__(self) -> None:
        database.initialize()

    # Project helpers ------------------------------------------------------------------
    def list_projects(self) -> list[Project]:
        with database.db_session() as conn:
            rows = conn.execute("SELECT id, name FROM projects ORDER BY created_at").fetchall()
            return [Project(id=row["id"], name=row["name"]) for row in rows]

    def get_project(self, project_id: int) -> Optional[Project]:
        """Get a single project by ID."""
        with database.db_session() as conn:
            row = conn.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                return None
            return Project(id=row["id"], name=row["name"])

    def create_project(self, name: str, description: str = None) -> Project:
        with database.db_session() as conn:
            cur = conn.execute(
                "INSERT INTO projects(name, description) VALUES (?, ?)",
                (name.strip(), description)
            )
            project_id = cur.lastrowid
            row = conn.execute("SELECT id, name, description FROM projects WHERE id = ?", (project_id,)).fetchone()
            return Project(id=row["id"], name=row["name"], description=row.get("description"))

    # Contact helpers ------------------------------------------------------------------
    def get_or_create_contact(self, email: str | None = None, name: str | None = None, phone: str | None = None) -> Contact:
        """Get existing contact or create new one."""
        if not email and not name:
            raise ValueError("Must provide at least email or name")

        with database.db_session() as conn:
            # Try to find existing contact by email
            if email:
                row = conn.execute(
                    "SELECT * FROM contacts WHERE email = ?", (email.lower().strip(),)
                ).fetchone()

                if row:
                    # Update name/phone if we have better info
                    updates = []
                    params = []
                    if name and not row["name"]:
                        updates.append("name = ?")
                        params.append(name.strip())
                    if phone and not row["phone"]:
                        updates.append("phone = ?")
                        params.append(phone.strip())

                    if updates:
                        params.append(row["id"])
                        conn.execute(
                            f"UPDATE contacts SET {', '.join(updates)}, updated_at = datetime('now') WHERE id = ?",
                            params
                        )
                        # Fetch updated row
                        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (row["id"],)).fetchone()

                    return _row_to_contact(row)

            # Create new contact
            cursor = conn.execute(
                "INSERT INTO contacts(name, email, phone) VALUES (?, ?, ?)",
                (name.strip() if name else None, email.lower().strip() if email else None, phone.strip() if phone else None)
            )
            row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return _row_to_contact(row)

    def get_contact(self, contact_id: int) -> Optional[Contact]:
        """Get a single contact by ID."""
        with database.db_session() as conn:
            row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if row is None:
                return None
            return _row_to_contact(row)

    def list_contacts(self) -> list[Contact]:
        """List all contacts."""
        with database.db_session() as conn:
            rows = conn.execute("SELECT * FROM contacts ORDER BY name, email").fetchall()
            return [_row_to_contact(row) for row in rows]

    def get_project_contacts(self, project_id: int) -> list[Contact]:
        """Get all contacts involved in a project."""
        with database.db_session() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.* FROM contacts c
                JOIN project_contacts pc ON c.id = pc.contact_id
                WHERE pc.project_id = ?
                ORDER BY c.name, c.email
                """,
                (project_id,)
            ).fetchall()
            return [_row_to_contact(row) for row in rows]

    # Communication helpers ------------------------------------------------------------
    def upsert_communication(
        self,
        comm_type: str,
        source_id: str,
        subject: str | None = None,
        snippet: str | None = None,
        timestamp: str | None = None,
        raw_path: Path | None = None,
        content: str | None = None,
    ) -> Communication:
        """Create or update a communication."""
        with database.db_session() as conn:
            conn.execute(
                """
                INSERT INTO communications(type, source_id, subject, snippet, timestamp, raw_path, content)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(type, source_id) DO UPDATE SET
                    subject = excluded.subject,
                    snippet = excluded.snippet,
                    timestamp = excluded.timestamp,
                    raw_path = excluded.raw_path,
                    content = excluded.content,
                    updated_at = datetime('now')
                """,
                (comm_type, source_id, subject, snippet, timestamp, str(raw_path) if raw_path else None, content),
            )
            row = conn.execute(
                "SELECT * FROM communications WHERE type = ? AND source_id = ?",
                (comm_type, source_id)
            ).fetchone()
            return _row_to_communication(row)

    def link_communication_to_project(self, communication_id: int, project_id: int, contact_id: int) -> None:
        """Link a communication to a project and contact."""
        with database.db_session() as conn:
            # Create link
            conn.execute(
                """
                INSERT OR IGNORE INTO project_communications(project_id, communication_id, contact_id)
                VALUES (?, ?, ?)
                """,
                (project_id, communication_id, contact_id)
            )

            # Update communication status
            conn.execute(
                """
                UPDATE communications
                SET status = 'assigned', remind_at = NULL, updated_at = datetime('now')
                WHERE id = ?
                """,
                (communication_id,)
            )

            # Add contact to project_contacts if not already there
            conn.execute(
                """
                INSERT OR IGNORE INTO project_contacts(project_id, contact_id)
                VALUES (?, ?)
                """,
                (project_id, contact_id)
            )

    def get_project_communications(self, project_id: int) -> list[tuple[Communication, Contact]]:
        """Get all communications for a project with associated contacts."""
        with database.db_session() as conn:
            rows = conn.execute(
                """
                SELECT c.*, co.* FROM communications c
                JOIN project_communications pc ON c.id = pc.communication_id
                JOIN contacts co ON pc.contact_id = co.id
                WHERE pc.project_id = ?
                ORDER BY datetime(c.timestamp) DESC
                """,
                (project_id,)
            ).fetchall()

            result = []
            for row in rows:
                # Split row into communication and contact parts
                comm = _row_to_communication(row)
                contact = Contact(
                    id=row["id"],  # This will be overwritten
                    name=row["name"],
                    email=row["email"],
                    phone=row["phone"],
                    notes=row.get("notes")
                )
                result.append((comm, contact))

            return result

    def get_contact_communications(self, contact_id: int, group_by_project: bool = True) -> dict | list:
        """Get all communications for a contact, optionally grouped by project."""
        with database.db_session() as conn:
            # Check if description column exists in projects table
            has_description = False
            try:
                conn.execute("SELECT description FROM projects LIMIT 1")
                has_description = True
            except:
                pass

            if has_description:
                rows = conn.execute(
                    """
                    SELECT c.*, p.id as project_id, p.name as project_name, p.description as project_description
                    FROM communications c
                    JOIN project_communications pc ON c.id = pc.communication_id
                    JOIN projects p ON pc.project_id = p.id
                    WHERE pc.contact_id = ?
                    ORDER BY p.name, datetime(c.timestamp) DESC
                    """,
                    (contact_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT c.*, p.id as project_id, p.name as project_name
                    FROM communications c
                    JOIN project_communications pc ON c.id = pc.communication_id
                    JOIN projects p ON pc.project_id = p.id
                    WHERE pc.contact_id = ?
                    ORDER BY p.name, datetime(c.timestamp) DESC
                    """,
                    (contact_id,)
                ).fetchall()

            if not group_by_project:
                return [_row_to_communication(row) for row in rows]

            # Group by project
            grouped = {}
            for row in rows:
                project_id = row["project_id"]
                if project_id not in grouped:
                    grouped[project_id] = {
                        "project": Project(
                            id=row["project_id"],
                            name=row["project_name"],
                            description=row["project_description"] if has_description and "project_description" in row.keys() else None
                        ),
                        "communications": []
                    }
                grouped[project_id]["communications"].append(_row_to_communication(row))

            return grouped

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
        """Store email in BOTH old and new schema (dual-write for migration)."""
        with database.db_session() as conn:
            # 1. Write to OLD emails table (backward compatibility)
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

            # 2. Write to NEW schema (communications + contacts)
            # Extract contact info
            name, email = extract_contact_info(parsed.sender)

            if email:  # Only create contact if we have an email
                # Get or create contact
                contact_row = conn.execute(
                    "SELECT id FROM contacts WHERE email = ?", (email,)
                ).fetchone()

                if contact_row:
                    contact_id = contact_row["id"]
                    # Update name if we have one and it's better
                    if name:
                        conn.execute(
                            """
                            UPDATE contacts SET name = COALESCE(name, ?), updated_at = datetime('now')
                            WHERE id = ?
                            """,
                            (name, contact_id)
                        )
                else:
                    # Create new contact
                    cursor = conn.execute(
                        "INSERT INTO contacts(name, email) VALUES (?, ?)",
                        (name, email)
                    )
                    contact_id = cursor.lastrowid

                # Create or update communication
                conn.execute(
                    """
                    INSERT INTO communications(type, source_id, subject, snippet, timestamp, raw_path)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(type, source_id) DO UPDATE SET
                        subject = excluded.subject,
                        snippet = excluded.snippet,
                        timestamp = excluded.timestamp,
                        raw_path = excluded.raw_path,
                        updated_at = datetime('now')
                    """,
                    ("email", parsed.message_id, parsed.subject, parsed.snippet, parsed.received_at, str(raw_storage_path))
                )

            # Return old format for backward compatibility
            row = conn.execute(
                "SELECT * FROM emails WHERE message_id = ?", (parsed.message_id,)
            ).fetchone()
            return _row_to_email(row)

    def set_email_project(self, email_id: int, project_id: int) -> None:
        """Assign email to project. Updates BOTH old and new schema."""
        with database.db_session() as conn:
            # 1. Update OLD emails table
            conn.execute(
                """
                UPDATE emails
                SET project_id = ?, status = 'assigned', remind_at = NULL, updated_at = datetime('now')
                WHERE id = ?
                """,
                (project_id, email_id),
            )

            # 2. Update NEW schema (if communication exists)
            # Get the email to find its message_id and sender
            email = conn.execute("SELECT message_id, sender FROM emails WHERE id = ?", (email_id,)).fetchone()
            if email:
                # Find corresponding communication
                comm = conn.execute(
                    "SELECT id FROM communications WHERE type = 'email' AND source_id = ?",
                    (email["message_id"],)
                ).fetchone()

                if comm:
                    # Get or create contact
                    name, email_addr = extract_contact_info(email["sender"])
                    if email_addr:
                        contact = conn.execute(
                            "SELECT id FROM contacts WHERE email = ?", (email_addr,)
                        ).fetchone()

                        if contact:
                            # Link communication to project
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO project_communications(project_id, communication_id, contact_id)
                                VALUES (?, ?, ?)
                                """,
                                (project_id, comm["id"], contact["id"])
                            )

                            # Update communication status
                            conn.execute(
                                """
                                UPDATE communications
                                SET status = 'assigned', remind_at = NULL, updated_at = datetime('now')
                                WHERE id = ?
                                """,
                                (comm["id"],)
                            )

                            # Add to project_contacts
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO project_contacts(project_id, contact_id)
                                VALUES (?, ?)
                                """,
                                (project_id, contact["id"])
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

    def get_emails_by_project(self, project_id: int) -> list[EmailEntry]:
        """Get all emails assigned to a specific project."""
        with database.db_session() as conn:
            rows = conn.execute(
                """
SELECT * FROM emails
WHERE project_id = ?
ORDER BY datetime(received_at) DESC
                """,
                (project_id,)
            ).fetchall()
        return [_row_to_email(row) for row in rows]

    def get_email_content(self, email_id: int) -> Optional[tuple[str, str]]:
        """Get the full content of an email from its raw file.

        Returns a tuple of (content, content_type) where content_type is 'text' or 'html'.
        """
        from email import policy
        from email.parser import BytesParser
        from email.message import EmailMessage

        email = self.get_email(email_id)
        if email is None or email.raw_path is None:
            return None

        raw_path = Path(email.raw_path)
        if not raw_path.exists():
            return None

        try:
            with raw_path.open("rb") as fp:
                message: EmailMessage = BytesParser(policy=policy.default).parse(fp)

            # Try to get HTML content first (richer format)
            html_parts = []
            text_parts = []

            if message.is_multipart():
                for part in message.walk():
                    content_type = part.get_content_type()
                    try:
                        if content_type == "text/html":
                            html_parts.append(part.get_content())
                        elif content_type == "text/plain":
                            text_parts.append(part.get_content())
                    except Exception:
                        continue
            else:
                content_type = message.get_content_type()
                try:
                    content = message.get_content()
                    if content_type == "text/html":
                        html_parts.append(content)
                    else:
                        text_parts.append(content)
                except Exception:
                    pass

            # Prefer HTML if available, otherwise use plain text
            if html_parts:
                return ("\n".join(filter(None, html_parts)).strip(), "html")
            elif text_parts:
                return ("\n".join(filter(None, text_parts)).strip(), "text")
            else:
                return None
        except Exception:
            return None

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
        """Ingest an email from an email source (Gmail)."""
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
