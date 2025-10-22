"""Migration script to convert existing emails to new schema."""
from __future__ import annotations

import re
from email.utils import parseaddr

from . import database


def extract_contact_info(sender: str | None) -> tuple[str | None, str | None]:
    """Extract name and email from sender string.

    Examples:
        'John Doe <john@example.com>' -> ('John Doe', 'john@example.com')
        'john@example.com' -> (None, 'john@example.com')
        'John Doe' -> ('John Doe', None)
    """
    if not sender:
        return None, None

    # Use email.utils.parseaddr for proper RFC parsing
    name, email = parseaddr(sender)

    # Clean up name (remove quotes, extra whitespace)
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


def get_or_create_contact(conn, name: str | None, email: str | None) -> int:
    """Get existing contact or create new one. Returns contact_id."""
    if not email and not name:
        raise ValueError("Must provide at least email or name")

    # Try to find existing contact by email
    if email:
        row = conn.execute(
            "SELECT id, name FROM contacts WHERE email = ?", (email,)
        ).fetchone()

        if row:
            # Update name if we have a better one (current is None and new is not)
            if name and not row["name"]:
                conn.execute(
                    "UPDATE contacts SET name = ?, updated_at = datetime('now') WHERE id = ?",
                    (name, row["id"])
                )
            return row["id"]

    # Create new contact
    cursor = conn.execute(
        """
        INSERT INTO contacts(name, email)
        VALUES (?, ?)
        """,
        (name, email)
    )
    return cursor.lastrowid


def migrate_emails_to_communications(dry_run: bool = False) -> dict:
    """Migrate existing emails to new schema.

    Returns statistics about the migration.
    """
    stats = {
        "emails_migrated": 0,
        "contacts_created": 0,
        "communications_created": 0,
        "project_links_created": 0,
        "errors": []
    }

    with database.db_session() as conn:
        # Get all emails that haven't been migrated yet
        emails = conn.execute(
            """
            SELECT e.* FROM emails e
            WHERE NOT EXISTS (
                SELECT 1 FROM communications c
                WHERE c.type = 'email' AND c.source_id = e.message_id
            )
            ORDER BY e.created_at
            """
        ).fetchall()

        print(f"Found {len(emails)} emails to migrate")

        if dry_run:
            print("DRY RUN - No changes will be made")

            # Show sample of what would be created
            for email in emails[:5]:
                name, email_addr = extract_contact_info(email["sender"])
                print(f"\nEmail: {email['subject']}")
                print(f"  From: {email['sender']}")
                print(f"  -> Would create contact: name={name}, email={email_addr}")
                print(f"  -> Would create communication: type=email, status={email['status']}")
                if email['project_id']:
                    print(f"  -> Would link to project {email['project_id']}")

            return stats

        # Actual migration
        for email in emails:
            try:
                # 1. Extract and create/get contact
                name, email_addr = extract_contact_info(email["sender"])

                if not email_addr:
                    # Skip emails without valid sender email
                    stats["errors"].append(f"Email {email['id']} has no valid sender email")
                    continue

                # Check if contact already exists
                existing_contact = conn.execute(
                    "SELECT id FROM contacts WHERE email = ?", (email_addr,)
                ).fetchone()

                if existing_contact:
                    contact_id = existing_contact["id"]
                else:
                    contact_id = get_or_create_contact(conn, name, email_addr)
                    stats["contacts_created"] += 1

                # 2. Create communication from email
                cursor = conn.execute(
                    """
                    INSERT INTO communications(
                        type, content, subject, snippet, timestamp, raw_path,
                        source_id, status, remind_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "email",
                        None,  # content will be loaded from raw_path when needed
                        email["subject"],
                        email["snippet"],
                        email["received_at"],
                        email["raw_path"],
                        email["message_id"],
                        email["status"],
                        email["remind_at"],
                        email["created_at"],
                        email["updated_at"]
                    )
                )
                communication_id = cursor.lastrowid
                stats["communications_created"] += 1

                # 3. Link communication to project (if assigned)
                if email["project_id"]:
                    conn.execute(
                        """
                        INSERT INTO project_communications(project_id, communication_id, contact_id)
                        VALUES (?, ?, ?)
                        """,
                        (email["project_id"], communication_id, contact_id)
                    )
                    stats["project_links_created"] += 1

                    # Also add contact to project_contacts if not already there
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO project_contacts(project_id, contact_id)
                        VALUES (?, ?)
                        """,
                        (email["project_id"], contact_id)
                    )

                stats["emails_migrated"] += 1

            except Exception as e:
                stats["errors"].append(f"Error migrating email {email['id']}: {e}")
                print(f"Error migrating email {email['id']}: {e}")
                continue

    return stats


def print_migration_stats(stats: dict) -> None:
    """Pretty print migration statistics."""
    print("\n" + "="*50)
    print("MIGRATION COMPLETE")
    print("="*50)
    print(f"Emails migrated:        {stats['emails_migrated']}")
    print(f"Contacts created:       {stats['contacts_created']}")
    print(f"Communications created: {stats['communications_created']}")
    print(f"Project links created:  {stats['project_links_created']}")

    if stats['errors']:
        print(f"\nErrors encountered:     {len(stats['errors'])}")
        for error in stats['errors'][:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(stats['errors']) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")
    else:
        print("\nNo errors encountered!")
    print("="*50 + "\n")


def main():
    """Run migration."""
    import sys

    dry_run = "--dry-run" in sys.argv

    print("Starting migration from emails to communications schema...")

    # Initialize database (creates new tables if needed)
    database.initialize()

    # Run migration
    stats = migrate_emails_to_communications(dry_run=dry_run)

    # Print results
    print_migration_stats(stats)

    if dry_run:
        print("This was a DRY RUN. Run without --dry-run to perform actual migration.")
    else:
        print("Migration complete! Old emails table is still intact for safety.")
        print("After verifying everything works, you can drop the emails table.")


if __name__ == "__main__":
    main()
