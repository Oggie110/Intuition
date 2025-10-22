"""Command line interface for the personal project manager app."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from .app import (
    ProjectManager,
    iter_pending_emails,
    prompt_user_for_email,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal email-to-project manager")
    subparsers = parser.add_subparsers(dest="command")

    fetch = subparsers.add_parser("fetch", help="Fetch emails from configured email sources")
    fetch.add_argument(
        "--max",
        type=int,
        default=10,
        help="Max emails to fetch per source (default: 10)",
    )
    fetch.add_argument(
        "--auto-triage",
        action="store_true",
        help="Automatically prompt for each fetched email",
    )

    subparsers.add_parser("setup-gmail", help="Setup Gmail OAuth authentication")

    subparsers.add_parser("list-sources", help="List configured email sources")

    subparsers.add_parser("list-projects", help="List all projects")

    list_emails = subparsers.add_parser("list-emails", help="List tracked emails")
    list_emails.add_argument(
        "--status",
        action="append",
        choices=["unassigned", "assigned", "snoozed", "ignored"],
        help="Filter by status (can be passed multiple times)",
    )

    subparsers.add_parser("check-reminders", help="Show emails whose snooze expired")

    return parser


def handle_list_projects(manager: ProjectManager) -> None:
    projects = manager.list_projects()
    if not projects:
        print("No projects yet. Fetch emails and create one during triage.")
        return
    for project in projects:
        print(f"[{project.id}] {project.name}")


def handle_list_emails(manager: ProjectManager, statuses: Iterable[str] | None) -> None:
    if statuses:
        entries = iter_pending_emails(manager, statuses)
    else:
        entries = iter_pending_emails(manager, ("unassigned", "snoozed", "assigned", "ignored"))

    if not entries:
        print("No emails tracked with the selected filters.")
        return

    for entry in entries:
        project_label = str(entry.project_id) if entry.project_id else "(unassigned)"
        print(
            f"[{entry.id}] status={entry.status} project={project_label} subject={entry.subject or '(no subject)'}"
        )


def handle_check_reminders(manager: ProjectManager) -> None:
    reminders = manager.list_pending_reminders()
    if not reminders:
        print("No reminders due right now.")
        return
    for entry in reminders:
        print(
            f"Reminder ready: email {entry.id} from {entry.sender or 'Unknown'} "
            f"subject {entry.subject or '(no subject)'}"
        )


def handle_setup_gmail() -> None:
    """Setup Gmail OAuth authentication."""
    from .email_sources import GmailSource, GMAIL_CREDENTIALS_PATH

    if not GMAIL_CREDENTIALS_PATH.exists():
        print(f"\nGmail OAuth credentials not found at: {GMAIL_CREDENTIALS_PATH}")
        print("\nTo setup Gmail integration:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select an existing one")
        print("3. Enable the Gmail API")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download the credentials JSON file")
        print(f"6. Save it to: {GMAIL_CREDENTIALS_PATH}")
        print("\nThen run this command again.")
        return

    print("Starting Gmail OAuth flow...")
    try:
        gmail = GmailSource()
        gmail.authenticate()
        print("\nGmail authentication successful!")
        print("You can now use 'fetch' command to retrieve emails from Gmail.")
    except Exception as e:
        print(f"\nError during Gmail authentication: {e}")
        raise SystemExit(1)


def handle_list_sources() -> None:
    """List configured email sources."""
    from .email_sources import get_available_sources

    sources = get_available_sources()
    if not sources:
        print("No email sources configured.")
        print("\nRun 'setup-gmail' to configure Gmail.")
        return

    print("Configured email sources:")
    for source in sources:
        print(f"  - {source.__class__.__name__}")


def handle_fetch(manager: ProjectManager, max_results: int, auto_triage: bool) -> None:
    """Fetch emails from all configured sources."""
    print(f"Fetching up to {max_results} emails per source...")

    ingested = manager.fetch_from_all_sources(max_per_source=max_results)

    if not ingested:
        print("\nNo new emails found.")
        return

    print(f"\nIngested {len(ingested)} new email(s).")

    if auto_triage:
        print("\nStarting auto-triage...")
        for email_entry in ingested:
            prompt_user_for_email(manager, email_entry)
    else:
        print("\nUse 'list-emails --status unassigned' to see them.")
        print("Or run 'fetch --auto-triage' to triage immediately.")


def main(args: list[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args)
    if not parsed.command:
        parser.print_help()
        return

    # Commands that don't need ProjectManager
    if parsed.command == "setup-gmail":
        handle_setup_gmail()
        return
    elif parsed.command == "list-sources":
        handle_list_sources()
        return

    # Commands that need ProjectManager
    manager = ProjectManager()

    if parsed.command == "fetch":
        handle_fetch(manager, parsed.max, parsed.auto_triage)
    elif parsed.command == "list-projects":
        handle_list_projects(manager)
    elif parsed.command == "list-emails":
        handle_list_emails(manager, parsed.status)
    elif parsed.command == "check-reminders":
        handle_check_reminders(manager)
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
