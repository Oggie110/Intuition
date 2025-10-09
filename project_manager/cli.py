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

    ingest = subparsers.add_parser("ingest", help="Ingest an .eml file and categorise it")
    ingest.add_argument("path", type=Path, help="Path to the .eml file")

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


def handle_ingest(manager: ProjectManager, path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    email_entry = manager.ingest_email_file(path)
    if email_entry is None:
        print("Sender is on the ignore list. Skipping.")
        return
    prompt_user_for_email(manager, email_entry)


def handle_list_projects(manager: ProjectManager) -> None:
    projects = manager.list_projects()
    if not projects:
        print("No projects yet. Use the ingest flow to create one.")
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


def main(args: list[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args)
    if not parsed.command:
        parser.print_help()
        return

    manager = ProjectManager()

    if parsed.command == "ingest":
        handle_ingest(manager, parsed.path)
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
