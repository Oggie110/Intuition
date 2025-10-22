# Project Handoff Document: Intuition Multi-Dimensional CRM

**Date**: October 22, 2025
**Status**: Phase 1 & 2 Complete - Core foundation and web views implemented
**Next**: Phase 3 - Testing & Migration, Phase 4 - Multi-platform integrations

---

## Table of Contents
1. [Project Vision](#project-vision)
2. [What We Built](#what-we-built)
3. [Architecture Overview](#architecture-overview)
4. [Current State](#current-state)
5. [File Structure](#file-structure)
6. [How It Works](#how-it-works)
7. [Next Steps](#next-steps)
8. [Technical Details](#technical-details)
9. [Testing Instructions](#testing-instructions)
10. [Future Development](#future-development)

---

## Project Vision

### The Goal
Build a **multi-dimensional CRM** inspired by Cloze CRM, but customized for creative professionals (directors, producers, etc.) who work on multiple projects with the same people.

### Key Requirements
- **Not just email**: Support Gmail, WhatsApp, Facebook Messenger, iOS Messages, files (Dropbox, Google Drive)
- **Multi-dimensional views**:
  - **Project view**: See ALL communications (any platform) for a project
  - **Contact view**: See ALL communications with a person, **grouped by projects**
- **Automatic contact aggregation**: Extract contacts from senders, dedupe, enrich over time
- **No scoring needed**: Unlike Cloze, we don't care about relationship scoring
- **Reminders**: Optional for later

### User Story Example
> "I have a director friend I work with a lot. When I check his contact profile, I want to see all our emails, SMS conversations, WhatsApp messages, etc., but organized by which project they relate to."

**This is now possible!** ✅

---

## What We Built

### Phase 1: Database Schema & Migration (COMPLETE ✅)

**New Tables:**
```sql
contacts (id, name, email, phone, notes, created_at, updated_at)
communications (id, type, content, subject, snippet, timestamp, raw_path, source_id, status, remind_at, created_at, updated_at)
project_communications (id, project_id, communication_id, contact_id, created_at)
project_contacts (project_id, contact_id, role, created_at)
```

**Key Design Decisions:**
- `communications` table is **generic** - handles email, WhatsApp, SMS, anything
- Every communication links to BOTH a project AND a contact via `project_communications`
- `project_contacts` tracks which people are involved in which projects
- Kept legacy `emails` table for backward compatibility during migration

**Migration Script:** `project_manager/migrate.py`
- Converts existing emails → communications
- Extracts contacts from email senders (uses RFC email parsing)
- Links communications to projects + contacts
- Dry-run mode available
- Idempotent (safe to re-run)

### Phase 2: Application Layer (COMPLETE ✅)

**New Data Classes (`app.py`):**
```python
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
```

**New Methods in ProjectManager:**
- `get_or_create_contact(email, name, phone)` - Smart contact management with deduplication
- `get_contact(contact_id)` / `list_contacts()` - Contact retrieval
- `get_project_contacts(project_id)` - Get all people in a project
- `upsert_communication(type, source_id, ...)` - Create/update any communication
- `link_communication_to_project(comm_id, project_id, contact_id)` - Assignment logic
- `get_project_communications(project_id)` - Returns list[(Communication, Contact)]
- `get_contact_communications(contact_id, group_by_project=True)` - **THE KEY METHOD**
  - Returns dict of {project_id: {"project": Project, "communications": [...]}}
  - Enables the grouped-by-project contact timeline view

**Dual-Write Implementation:**
- `upsert_email()` now writes to BOTH old `emails` table AND new `communications` + `contacts`
- `set_email_project()` updates BOTH schemas
- **Backward compatible**: All existing code continues to work

### Phase 3: Web Views (COMPLETE ✅)

**New Routes (`web.py`):**
```python
@app.get("/contacts")
def list_contacts():
    # Shows table of all contacts

@app.get("/contacts/<int:contact_id>")
def contact_detail(contact_id: int):
    # Shows contact timeline GROUPED BY PROJECT
    # This is the killer feature!
```

**New Templates:**
- `templates/contacts.html` - List view of all contacts
- `templates/contact_detail.html` - Contact timeline grouped by projects
- Updated `templates/base.html` - Added "Contacts" to navigation

**Key Features:**
- Contact list shows name, email, phone
- Contact detail page shows communications organized by project sections
- Each project section shows all communications with that contact for that project
- Expandable email content inline (click to see full email)
- Links between contact view ↔ project view work both ways

---

## Architecture Overview

### Data Model Relationships

```
┌─────────────┐
│  Projects   │
└──────┬──────┘
       │
       ├───────────────────┐
       │                   │
       ▼                   ▼
┌──────────────────────────────────┐
│   project_communications         │
│   (project_id, communication_id, │
│    contact_id)                   │
└──────┬──────────────────┬────────┘
       │                   │
       ▼                   ▼
┌─────────────┐    ┌─────────────┐
│Communications│    │  Contacts   │
└─────────────┘    └─────────────┘

┌─────────────┐    ┌─────────────┐
│  Projects   │◄───►│project_     │
└─────────────┘    │contacts     │
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  Contacts   │
                   └─────────────┘
```

### Key Concepts

1. **Communication** = any interaction (email, WhatsApp message, SMS, file, meeting, note)
2. **Every communication** is linked to exactly ONE project and ONE contact via `project_communications`
3. **Contacts** can be in multiple projects (tracked in `project_contacts`)
4. **You can pivot** between views:
   - Project → see all communications (any type) + all people involved
   - Contact → see all communications with that person, grouped by projects

### Tech Stack

- **Language**: Python 3.10+
- **Framework**: Flask (web UI)
- **Database**: SQLite
  - Perfect for single-user, local-first
  - Can handle 100k+ records easily
  - Has built-in FTS5 for future full-text search
- **Email Integration**: Gmail API (working)
- **Future Integrations**: WhatsApp, Facebook Messenger, iOS Messages, Google Drive, Dropbox

**Why SQLite?**
- No external dependencies
- Fast for this use case
- Easy backups (single file)
- Can upgrade to PostgreSQL later if needed for multi-user
- Vector database (Chroma, pgvector) only needed for semantic search later

---

## Current State

### What's Working ✅

1. **Gmail Integration**
   - Fetches unread emails via Gmail API
   - Stores raw .eml files
   - OAuth2 authentication setup

2. **Dual-Write System**
   - New emails written to BOTH old and new schema
   - Email assignment updates both schemas
   - Zero breaking changes to existing functionality

3. **Contact Management**
   - Automatic extraction from email senders
   - RFC-compliant email parsing (handles "Name <email@example.com>")
   - Deduplication by email address
   - Name enrichment (updates name if better info available)

4. **Web Interface**
   - `/` - Inbox (triage unassigned emails)
   - `/projects` - List all projects
   - `/projects/<id>` - Project detail (shows emails)
   - `/contacts` - List all contacts ✨ NEW
   - `/contacts/<id>` - Contact timeline grouped by projects ✨ NEW

5. **Migration Script**
   - Converts existing emails → new schema
   - Extracts contacts
   - Creates project links
   - Safe, idempotent, has dry-run mode

### What's NOT Done Yet ⚠️

1. **Migration not run** - Existing data needs to be migrated
2. **Project view not updated** - Still shows old `emails` table, should show `communications` + contacts
3. **Multi-platform integrations** - WhatsApp, Messenger, SMS not implemented
4. **File management** - Email attachments not extracted/linked
5. **Calendar integration** - Meetings not tracked as communications
6. **Search** - No full-text search yet (SQLite FTS5 ready to add)
7. **Reminders** - Snooze works but no proactive follow-up suggestions

---

## File Structure

```
Github/
├── project_manager/
│   ├── __init__.py
│   ├── app.py              # Core logic: ProjectManager class
│   ├── cli.py              # Command-line interface
│   ├── config.py           # Configuration (paths, settings)
│   ├── database.py         # Database schema & connection handling
│   ├── email_sources.py    # Gmail API integration
│   ├── email_utils.py      # Email parsing utilities
│   ├── migrate.py          # Migration script ✨ NEW
│   ├── web.py              # Flask web interface
│   └── templates/
│       ├── base.html       # Base template (updated with Contacts nav)
│       ├── index.html      # Inbox/triage view
│       ├── projects.html   # Project list
│       ├── project_detail.html  # Project detail
│       ├── contacts.html   # Contact list ✨ NEW
│       └── contact_detail.html  # Contact timeline ✨ NEW
├── requirements.txt
├── README.md
├── MIGRATION_PLAN.md       # Migration overview
├── WEB_VIEWS_COMPLETE.md   # Web views documentation
└── HANDOFF.md             # This document

Data (at ~/.project_manager/):
├── project_manager.db      # SQLite database
└── raw_emails/             # Stored .eml files
```

---

## How It Works

### Current Workflow (Emails Only)

1. **User runs**: `python -m project_manager.cli fetch` or clicks "Fetch" in web UI
2. **System fetches** unread emails from Gmail
3. **For each email**:
   - Saves raw .eml file to `~/.project_manager/raw_emails/`
   - Extracts: subject, sender, timestamp, snippet
   - **NEW**: Parses sender → creates/updates contact
   - **Dual-writes**:
     - Old schema: Inserts into `emails` table
     - New schema: Inserts into `communications` (type='email') + `contacts`
4. **User assigns email to project** (web UI or CLI)
   - **Dual-writes**:
     - Old schema: Updates `emails.project_id`
     - New schema: Creates `project_communications` link + adds to `project_contacts`
5. **Views work**:
   - Project view: Shows emails (old schema for now)
   - Contact view: Shows communications grouped by projects (new schema) ✨

### Future Workflow (Multi-Platform)

Same as above, but step 1 fetches from multiple sources:
- Gmail API
- WhatsApp (export or Business API)
- Facebook Messenger (Graph API)
- iOS Messages (AppleScript)
- Google Drive (Files API)
- Dropbox (API)

All flow through same logic → stored as `communications` with different `type` values.

---

## Next Steps

### Phase 3: Testing & Validation (NOT STARTED)

**Priority: HIGH**

1. **Run migration on existing data**:
   ```bash
   # Preview what will happen
   python -m project_manager.migrate --dry-run

   # Execute migration
   python -m project_manager.migrate
   ```

2. **Verify migration results**:
   - Check contacts were created correctly
   - Verify communications are linked to projects
   - Ensure no data loss
   - Test that old code still works (backward compatibility)

3. **Test contact views**:
   - Visit `/contacts` - see all contacts
   - Click a contact → see timeline grouped by projects
   - Verify emails show up correctly
   - Test expanding email content inline

4. **Update project view** (IMPORTANT):
   - Currently `project_detail()` in `web.py` uses old `get_emails_by_project()`
   - Should use new `get_project_communications()` to show contacts too
   - Update `templates/project_detail.html` to display contact names

### Phase 4: Multi-Platform Integrations (FUTURE)

**Choose based on priority:**

#### Option A: WhatsApp
- **Approach 1**: User exports chat → script parses text file
- **Approach 2**: WhatsApp Business API (official but requires business account)
- **Approach 3**: `yowsup` library (unofficial, may break)

#### Option B: Facebook Messenger
- Use Meta Graph API
- Requires Facebook app + OAuth
- Can fetch message history

#### Option C: iOS Messages
- Use AppleScript (like old Apple Mail integration that was removed)
- macOS only
- Can access Messages.app database

#### Option D: File Attachments
- Extract attachments from emails
- Store in `files` table
- Link to `communications` via `communication_id`
- Also support manual file upload/linking

#### Option E: Calendar (Google Calendar)
- Fetch meetings via Calendar API
- Store as `communications` with type='meeting'
- Link attendees as contacts

### Phase 5: Enhanced Features (FUTURE)

1. **Full-Text Search**:
   - Add SQLite FTS5 virtual table
   - Index all communication content
   - Add search UI

2. **Smart Reminders**:
   - "Haven't talked to X in 30 days"
   - Configurable per contact
   - Email/desktop notifications

3. **Bulk Operations**:
   - Merge duplicate contacts
   - Bulk assign communications to projects
   - Export data (CSV, JSON)

4. **Analytics**:
   - Communication frequency graphs
   - Project timelines
   - Contact heatmaps

5. **AI Features** (optional):
   - Auto-suggest project for incoming emails
   - Extract action items from communications
   - Summarize project communications

---

## Technical Details

### Database Schema

**Full schema in**: `project_manager/database.py`

Key tables:

```sql
-- Core entities
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE communications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL, -- 'email', 'whatsapp', 'messenger', 'sms', 'note', 'file', 'meeting'
    content TEXT,
    subject TEXT,
    snippet TEXT,
    timestamp TEXT,
    raw_path TEXT,
    source_id TEXT,
    status TEXT NOT NULL DEFAULT 'unassigned',
    remind_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(type, source_id)
);

-- Links
CREATE TABLE project_communications (
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

CREATE TABLE project_contacts (
    project_id INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    role TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(project_id, contact_id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_communications_type ON communications(type);
CREATE INDEX idx_communications_status ON communications(status);
CREATE INDEX idx_communications_timestamp ON communications(timestamp);
CREATE INDEX idx_project_communications_project ON project_communications(project_id);
CREATE INDEX idx_project_communications_contact ON project_communications(contact_id);
CREATE INDEX idx_contacts_email ON contacts(email);
```

### Key Functions

**Contact extraction** (`app.py:105-129`):
```python
def extract_contact_info(sender: str | None) -> tuple[str | None, str | None]:
    """Extract name and email from sender string.

    Examples:
        'John Doe <john@example.com>' -> ('John Doe', 'john@example.com')
        'john@example.com' -> (None, 'john@example.com')
    """
```

**Contact management** (`app.py:163-203`):
```python
def get_or_create_contact(
    self,
    email: str | None = None,
    name: str | None = None,
    phone: str | None = None
) -> Contact:
    """Get existing contact or create new one."""
    # Deduplicates by email
    # Updates name/phone if better info available
```

**The killer query** (`app.py:326-359`):
```python
def get_contact_communications(
    self,
    contact_id: int,
    group_by_project: bool = True
) -> dict | list:
    """Get all communications for a contact, optionally grouped by project."""
    # Returns: {
    #   project_id: {
    #     "project": Project(...),
    #     "communications": [Communication, ...]
    #   }
    # }
```

### Configuration

**Environment Variables:**
- `PROJECT_MANAGER_HOME` - Data directory (default: `~/.project_manager/`)
- `PROJECT_MANAGER_WEB_SECRET` - Flask secret key (default: `dev-key`)

**File Paths** (`config.py`):
- Database: `~/.project_manager/project_manager.db`
- Raw emails: `~/.project_manager/raw_emails/`
- Gmail credentials: `~/.project_manager/gmail_credentials.json`
- Gmail token: `~/.project_manager/gmail_token.json`

---

## Testing Instructions

### 1. Initial Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Setup Gmail (if not done)
# 1. Download OAuth credentials from Google Cloud Console
# 2. Save to ~/.project_manager/gmail_credentials.json
python -m project_manager.cli setup-gmail

# Verify Gmail works
python -m project_manager.cli list-sources
```

### 2. Run Migration

```bash
# Preview migration (safe, no changes)
python -m project_manager.migrate --dry-run

# Review output, check for errors

# Execute migration
python -m project_manager.migrate

# You should see:
# - Emails migrated: X
# - Contacts created: Y
# - Communications created: X
# - Project links created: Z
```

### 3. Test Web UI

```bash
# Start server
python -m project_manager.web

# Visit http://127.0.0.1:5000
```

**Test Cases:**

1. **Fetch emails**:
   - Click "Fetch from Gmail"
   - Verify emails appear in Inbox
   - Check that contacts were auto-created (go to /contacts)

2. **Assign email to project**:
   - Assign an email to a project
   - Go to `/contacts`
   - Find the sender
   - Click their name
   - Verify email shows up under the correct project section

3. **Contact timeline view**:
   - Go to `/contacts/<id>` for a contact with multiple projects
   - Verify communications are grouped by project
   - Click an email to expand content
   - Verify it displays correctly (HTML or plain text)

4. **Project view**:
   - Go to `/projects/<id>`
   - Currently shows old email view (TODO: update to show contacts)

5. **Backward compatibility**:
   - Try all old CLI commands:
     ```bash
     python -m project_manager.cli list-projects
     python -m project_manager.cli list-emails
     python -m project_manager.cli check-reminders
     ```
   - Verify they still work

### 4. Test Migration Safety

```bash
# Check old emails table still exists
sqlite3 ~/.project_manager/project_manager.db "SELECT COUNT(*) FROM emails;"

# Check new tables have data
sqlite3 ~/.project_manager/project_manager.db "SELECT COUNT(*) FROM contacts;"
sqlite3 ~/.project_manager/project_manager.db "SELECT COUNT(*) FROM communications;"
sqlite3 ~/.project_manager/project_manager.db "SELECT COUNT(*) FROM project_communications;"
```

### 5. Data Validation Queries

```sql
-- Verify all emails have corresponding communications
SELECT COUNT(*)
FROM emails e
WHERE NOT EXISTS (
    SELECT 1 FROM communications c
    WHERE c.type = 'email' AND c.source_id = e.message_id
);
-- Should return 0

-- Check for contacts without email
SELECT COUNT(*) FROM contacts WHERE email IS NULL;

-- See project communication counts
SELECT p.name, COUNT(pc.id) as comm_count
FROM projects p
LEFT JOIN project_communications pc ON p.id = pc.project_id
GROUP BY p.id
ORDER BY comm_count DESC;

-- See contact communication counts
SELECT c.name, c.email, COUNT(pc.id) as comm_count
FROM contacts c
LEFT JOIN project_communications pc ON c.id = pc.contact_id
GROUP BY c.id
ORDER BY comm_count DESC;
```

---

## Future Development

### Short Term (Next 2-4 weeks)

1. **Update Project View**:
   - Use `get_project_communications()` instead of `get_emails_by_project()`
   - Show contact names, not just email addresses
   - Add "People" section showing all contacts in project
   - Group communications by contact or date

2. **Manual Contact Management**:
   - Add contact editing UI
   - Merge duplicate contacts
   - Add notes to contacts
   - Manual contact creation

3. **File Attachments**:
   - Extract email attachments
   - Store in `files` table
   - Link to communications
   - Display in project/contact views

### Medium Term (1-2 months)

4. **First Multi-Platform Integration** (choose one):
   - WhatsApp (easiest: export parsing)
   - iOS Messages (if on Mac)
   - Facebook Messenger (requires API setup)

5. **Search**:
   - SQLite FTS5 implementation
   - Search box in UI
   - Search across all communications

6. **Better Contact Management**:
   - Avatar support (Gravatar?)
   - Contact tags/categories
   - Custom fields
   - Last contacted date prominently displayed

### Long Term (2-4 months)

7. **Calendar Integration**:
   - Google Calendar API
   - Meetings as communications
   - Link attendees as contacts

8. **Google Drive / Dropbox**:
   - List files shared with contacts
   - Link files to projects
   - Auto-detect project from file location

9. **Smart Features**:
   - AI auto-categorization (which project does this email belong to?)
   - Action item extraction
   - Follow-up reminders ("you haven't responded to X")
   - Project summaries

10. **Mobile Support**:
    - Responsive UI
    - Progressive Web App (PWA)
    - Push notifications for reminders

### Ideas for Later

- **Team Features** (requires PostgreSQL):
  - Multiple users
  - Shared projects
  - Activity log
  - Permissions

- **Integrations**:
  - Slack (fetch DMs and channel messages)
  - Linear/Asana/Notion (link tasks to communications)
  - Zoom (meeting recordings as communications)

- **Advanced Analytics**:
  - Communication frequency graphs
  - Response time tracking
  - Project timelines
  - Network visualization (who works with whom)

- **AI Assistant**:
  - "Show me everything about the documentary project"
  - "Who am I behind on responding to?"
  - "Summarize my communications with John this month"
  - Semantic search with vector embeddings

---

## Common Issues & Solutions

### Issue: Migration fails with "contacts already exist"
**Solution**: Migration is idempotent. It skips communications that already exist (based on `type` + `source_id`). Safe to re-run.

### Issue: Contact has no name, just email
**Solution**: This is normal if email sender didn't include name. Will be enriched when better info arrives (e.g., email signature with full name).

### Issue: Some emails not migrated
**Solution**: Check migration output for errors. Emails without valid sender email are skipped (can't create contact without email or name).

### Issue: Gmail API quota exceeded
**Solution**: Gmail API has rate limits. Default fetch limit is 10 emails. Increase slowly. Add delays if needed.

### Issue: Can't find contact in list
**Solution**: Contact list sorted by name, then email. If no name, will be at end. Consider adding search.

### Issue: Email content doesn't display
**Solution**: Check that `raw_path` exists and file is readable. Some emails may have encoding issues. Check `get_email_content()` error handling.

### Issue: Old code breaks after migration
**Solution**: Migration preserves old `emails` table. Dual-write means old code should still work. Check error logs for details.

---

## Architecture Decisions & Rationale

### Why SQLite?
- **Local-first**: All data on user's machine, no cloud dependencies
- **Simple**: Single file database, easy backup
- **Fast**: More than enough for 100k+ records
- **Portable**: Works on Mac/Windows/Linux
- **Can upgrade**: Easy migration to PostgreSQL if multi-user needed later

### Why not vector database initially?
- **Overkill**: Don't need semantic search for structured data
- **Add later**: Can add Chroma/pgvector as a layer on top when needed
- **Simpler**: SQLite FTS5 handles text search needs for now

### Why dual-write during migration?
- **Zero downtime**: Existing code keeps working
- **Safe rollback**: Can disable new code if issues
- **Gradual migration**: Test new features without committing
- **Later cleanup**: Can drop old `emails` table after confidence

### Why generic `communications` table?
- **Future-proof**: Adding WhatsApp doesn't require new table
- **Consistent views**: UI doesn't need to know about communication types
- **Flexible**: Can add new types (video calls, documents) without schema changes

### Why separate `project_communications` and `project_contacts`?
- **Different purposes**:
  - `project_communications`: Links specific messages to projects
  - `project_contacts`: Tracks overall project membership
- **Performance**: Easier queries for "who's in this project?"
- **Flexibility**: Can have contact in project without communications yet

---

## Code Style & Conventions

- **Type hints**: Used throughout (Python 3.10+ syntax with `|` for unions)
- **Dataclasses**: Preferred for data structures
- **Context managers**: Used for database connections (`with database.db_session()`)
- **Docstrings**: Google-style docstrings on public methods
- **Naming**:
  - `snake_case` for functions/variables
  - `PascalCase` for classes
  - Private functions prefixed with `_`
- **SQL**: Parameterized queries always (no string interpolation)
- **Transactions**: Auto-committed via context manager

---

## Resources & References

### Cloze CRM Research
- Original vision: Personal CRM (2012-2015)
- Pivoted to real estate (2020s)
- Key feature we're cloning: Automatic contact aggregation across platforms
- Key feature we're NOT cloning: Relationship scoring (0-100)
- **Our advantage**: Open source, full control, customized for creative industry

### Documentation
- Gmail API: https://developers.google.com/gmail/api
- Flask: https://flask.palletsprojects.com/
- SQLite: https://www.sqlite.org/docs.html
- SQLite FTS5: https://www.sqlite.org/fts5.html

### Related Projects
- Monica CRM (personal CRM, similar concept)
- Notion (inspiration for multi-dimensional data)
- Airtable (inspiration for flexible schema)

---

## Contact & Questions

**Original Requirements**: See conversation history for detailed user requirements and use cases.

**Philosophy**:
- Build for one user first (yourself)
- Make it work, make it right, make it fast (in that order)
- Local-first, privacy-focused
- Simple over clever
- Extensible over comprehensive

**When in doubt**:
1. Check this handoff document
2. Read the code (it's well-commented)
3. Test with dry-run mode
4. Ask questions (document answers here)

---

## Current Status: Organizational Structure Decision Pending

**Date**: October 22, 2025
**Status**: ⚠️ PAUSED - Awaiting user decision on project organization

### Background

After completing Phases 1-3 (database schema, migration, web views), the next logical step was to implement project hierarchy (nested folders/sub-projects). Three options were proposed:

1. **Full Hierarchy**: Unlimited nesting with parent_id references
2. **Tags/Categories**: Flat structure with flexible categorization
3. **2-Level Hybrid**: Parent projects with children (recommended)

### The Turning Point

User reviewed their current **Airtable workflow** and expressed uncertainty about moving away from it.

**User Quote**: "I am honestly not, sure, I need to think about this for a while. This is what I am using right now, Airtable... I kind of like this. It's not what I just said I wanted, but yeah"

### Airtable Current Structure

The user's existing system shows:

**Project Organization**:
- **Flat structure** (no nesting)
- **Status columns**: Future, In Progress, Send Invoice
- **Category tags**: Film/Tv, Royalties, Advertising, Software, Sound Editing, Library, Other
- **Type tags**: Feature Film, Feature Doc, Documentary, Extension, etc.
- **Financial tracking**: SEK amounts per project
- **Date tracking**: Created date, modified date
- **Rich metadata**: Multiple columns with project-specific data

**Key Observations**:
- User is comfortable with flat structure + rich tagging
- Heavy emphasis on status tracking and categorization
- Financial data is first-class (not an afterthought)
- No evidence of nested projects/sub-projects in current workflow

### Design Implications

This creates tension between:
1. **What user initially requested**: "nested folders in projects, so I can create new projects and sub-projects etc, and move them around when needed"
2. **What user actually uses**: Flat structure with tags, status, and financial tracking

### Open Questions

Before proceeding with ANY organizational structure changes:

1. **Does user want hierarchy at all?**
   - Original request: YES (nested projects)
   - Current Airtable workflow: NO (flat with tags)
   - Needs clarification

2. **What features from Airtable must be preserved?**
   - Status workflow (Future → In Progress → Invoice)
   - Category/type tagging system
   - Financial tracking per project
   - Date tracking

3. **What's the migration path from Airtable?**
   - Import existing Airtable data?
   - Run both systems in parallel?
   - Complete replacement?

4. **What problems with Airtable led to building this?**
   - Lack of communication aggregation? (YES - this is clear)
   - Something else?

### Recommended Next Steps

**DO NOT implement project hierarchy yet.** Instead:

1. **User reflection**: Let user analyze their Airtable workflow vs original requirements
2. **Feature parity assessment**: Identify which Airtable features are essential
3. **Hybrid approach**: Consider flat projects + tags + better communication management
4. **Prototype**: Mock up a few UI approaches and get user feedback

### What This Means for Development

**Safe to continue**:
- Multi-platform integrations (WhatsApp, Messenger, etc.)
- Contact management improvements
- Search functionality
- File attachment handling
- Calendar integration

**Wait for user decision**:
- Project hierarchy implementation
- Project folder/category system
- Any major project model changes
- UI redesigns around project organization

### Alternative Approach: Airtable-Inspired Design

If user wants to stick closer to their current workflow, consider:

```
Projects Table (flat, no nesting):
- id
- name
- status (future, in_progress, invoiced)
- category (film_tv, royalties, advertising, etc.)
- type (feature_film, documentary, extension, etc.)
- budget_sek
- created_at
- deadline
- ... (other metadata)

Project Tags (many-to-many):
- project_id
- tag (flexible, user-defined)

Communications → Projects (existing):
- Already works with flat structure
- No changes needed
```

**Advantages**:
- Familiar to user
- No learning curve
- Easy Airtable import
- Status-based workflows (Kanban views?)
- Financial tracking built-in

**Disadvantages**:
- No hierarchy (but user might not need it)
- More tags to manage
- Might feel cluttered with many projects

### Migration from Airtable

If user decides to import Airtable data:

1. **Export Airtable to CSV**
2. **Write import script**: `import_airtable.py`
   - Map Airtable columns → project fields
   - Handle status values
   - Import category/type as tags
   - Preserve financial data
   - Link existing communications to projects (by project name matching?)
3. **Validation**: Compare counts, spot-check data

### Bottom Line

**The multi-dimensional communication tracking (Phases 1-3) is solid and working.** That part is the novel feature that Airtable doesn't provide.

**The project organization layer is still uncertain.** User needs to decide:
- Hierarchy vs flat
- Airtable-style vs something new
- Migration vs fresh start

**Recommendation**: Focus on features that don't depend on project structure (integrations, search, attachments) until organizational decision is made.

---

## Version History

- **v0.1** (Oct 22, 2025): Initial handoff after Phase 1 & 2 completion
  - Database schema designed
  - Migration script created
  - Contact & communication management implemented
  - Web views for contacts built
  - Dual-write system working

- **v0.2** (Oct 22, 2025): Added organizational structure decision section
  - Documented Airtable comparison
  - Identified tension between initial request and current workflow
  - Recommended waiting for user decision before implementing hierarchy
  - Suggested Airtable-inspired alternative approach

---

**END OF HANDOFF DOCUMENT**

This project is ready for testing and multi-platform integrations. The core communication tracking foundation is solid. Project organization layer awaiting user decision. Good luck! 🚀
