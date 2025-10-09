# Personal Project Manager MVP

This repository contains a minimal email-driven project management helper written in Python. The focus is on quickly sorting inbound emails into personal projects without the overhead of multi-user features.

## Features

- Store projects and incoming email metadata in a lightweight SQLite database.
- Ingest `.eml` files (for example exported or forwarded emails) and prompt you to:
  1. assign the message to an existing project,
  2. create a brand-new project for it,
  3. snooze the decision for 1 day, 1 week, or 1 month, or
  4. ignore all future emails from the sender.
- Keep the raw email file so you can refer back to the original content later.
- List projects, inspect tracked emails, and surface snoozed emails whose reminders are due.

## Getting started

1. **Install Python 3.10+** (the app uses only the standard library).
2. (Optional) Set a custom storage directory by exporting `PROJECT_MANAGER_HOME=/path/to/storage`. Otherwise data lives in `~/.project_manager/`.
3. Run the CLI through the module entry point:

   ```bash
   python -m project_manager.cli --help
   ```

The first command invocation initializes the SQLite database and required folders automatically.

## Typical workflow

1. Save an interesting email as an `.eml` file (most email clients provide this feature) or pipe a forwarded message to disk.
2. Ingest it:

   ```bash
   python -m project_manager.cli ingest path/to/message.eml
   ```

3. Follow the interactive prompt to choose the appropriate project action.
4. Later on, review the state of your inbox triage:

   ```bash
   # List every project
   python -m project_manager.cli list-projects

   # Show all tracked emails (filter with --status if desired)
   python -m project_manager.cli list-emails

   # Bring back anything whose snooze expired
   python -m project_manager.cli check-reminders
   ```

Raw emails are copied to `<storage>/raw_emails/` for future reference.

## Future directions

This MVP deliberately avoids handling authentication or talking directly to an email provider. You can extend it by adding an IMAP fetcher, integrating with an automation tool like Zapier, or layering a simple GUI on top of the CLI.
