# Personal Project Manager MVP

This repository contains a minimal email-driven project management helper written in Python. The focus is on quickly sorting inbound emails into personal projects without the overhead of multi-user features.

## Features

- **Auto-fetch emails** from Gmail
- Store projects and incoming email metadata in a lightweight SQLite database
- Triage emails interactively or via web dashboard:
  1. Assign the message to an existing project
  2. Create a brand-new project for it
  3. Snooze the decision for 1 day, 1 week, or 1 month
  4. Ignore all future emails from the sender
- Keep the raw email content for reference
- List projects, inspect tracked emails, and surface snoozed emails whose reminders are due
- Lightweight Flask-powered web dashboard with one-click email fetching

## Getting started

1. **Install Python 3.10+**

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   This installs Flask (for web UI) and Gmail API libraries.

3. (Optional) Set a custom storage directory by exporting `PROJECT_MANAGER_HOME=/path/to/storage`. Otherwise data lives in `~/.project_manager/`.

4. Run the CLI through the module entry point:

   ```bash
   python -m project_manager.cli --help
   ```

The first command invocation initializes the SQLite database and required folders automatically.

## Gmail Setup

1. **Enable Gmail API in Google Cloud Console:**
   - Go to https://console.cloud.google.com/
   - Create a new project or select an existing one
   - Enable the Gmail API
   - Create OAuth 2.0 credentials (Desktop app type)
   - Download the credentials JSON file

2. **Configure the app:**
   ```bash
   # Save credentials to ~/.project_manager/gmail_credentials.json
   cp ~/Downloads/credentials.json ~/.project_manager/gmail_credentials.json

   # Run OAuth setup (opens browser for authentication)
   python -m project_manager.cli setup-gmail
   ```

3. **Verify configuration:**
   ```bash
   python -m project_manager.cli list-sources
   ```

## Typical workflow

### Fetch and triage emails

1. Fetch emails from all configured sources:

   ```bash
   python -m project_manager.cli fetch
   ```

   Or fetch and immediately triage interactively:

   ```bash
   python -m project_manager.cli fetch --auto-triage
   ```

   Customize the batch size:

   ```bash
   python -m project_manager.cli fetch --max 20 --auto-triage
   ```

2. Follow the interactive prompts to assign each email to a project.

### Managing your projects

```bash
# List every project
python -m project_manager.cli list-projects

# Show all tracked emails (filter with --status if desired)
python -m project_manager.cli list-emails

# Bring back anything whose snooze expired
python -m project_manager.cli check-reminders
```

Raw emails are stored in `<storage>/raw_emails/` for future reference.

## Web interface

Prefer point-and-click triage? Start the Flask dev server and visit the dashboard:

```bash
python -m project_manager.web
```

Then open <http://127.0.0.1:5000/>.

The web interface provides:
- **One-click email fetching** from Gmail with configurable batch size
- Assign emails to existing projects or create new ones on the fly
- Snooze decisions for a later date (1 day, 1 week, 1 month)
- Ignore senders entirely
- Browse and manage all projects at `/projects`

## Future directions

Possible enhancements:
- IMAP support for other email providers
- Automated periodic fetching (cron job/background service)
- Email threading and conversation grouping
- Rich text email preview
- Mobile-friendly interface
- Integration with task management tools (Todoist, Notion, etc.)
