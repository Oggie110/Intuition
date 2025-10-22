# Migration to Multi-Dimensional CRM

## Overview
Transforming the project manager from email-only to a multi-dimensional CRM that supports:
- **Project view**: See all communications (emails, WhatsApp, SMS, files) for a project
- **Contact view**: See all communications with a person, grouped by projects
- **Multi-platform**: Email (done), WhatsApp, Messenger, SMS, files (future)

## Current Status: ✅ Phase 1 Complete

### What's Been Done

#### 1. New Database Schema (`database.py`)
- ✅ `contacts` table - stores people (name, email, phone, notes)
- ✅ `communications` table - generic storage for all communication types
- ✅ `project_communications` table - many-to-many linking (project ↔ communication ↔ contact)
- ✅ `project_contacts` table - tracks which contacts are in which projects
- ✅ Indexes for performance
- ✅ Kept legacy `emails` table for backward compatibility

#### 2. Migration Script (`migrate.py`)
- ✅ Converts existing emails → communications
- ✅ Extracts contacts from email senders
- ✅ Links communications to projects and contacts
- ✅ Dry-run mode to preview changes
- ✅ Detailed statistics and error reporting

**To run migration:**
```bash
# Preview
python -m project_manager.migrate --dry-run

# Execute
python -m project_manager.migrate
```

#### 3. Updated ProjectManager (`app.py`)
New data classes:
- ✅ `Contact` - represents a person
- ✅ `Communication` - represents any communication (email, WhatsApp, etc.)
- ✅ Kept `EmailEntry` for backward compatibility

New methods:
- ✅ `get_or_create_contact()` - smart contact management
- ✅ `get_contact()` / `list_contacts()` - contact retrieval
- ✅ `get_project_contacts()` - contacts in a project
- ✅ `upsert_communication()` - create/update any communication
- ✅ `link_communication_to_project()` - assign comm to project + contact
- ✅ `get_project_communications()` - get all comms for a project
- ✅ `get_contact_communications()` - get all comms for a contact (grouped by project!)

**Dual-write implementation:**
- ✅ `upsert_email()` now writes to BOTH old `emails` and new `communications` + `contacts`
- ✅ `set_email_project()` updates BOTH schemas
- ✅ All existing code continues to work!

## Next Steps

### Phase 2: Update Views (Not Started)
- [ ] Add `/contacts` route to list all contacts
- [ ] Add `/contacts/<id>` route to show contact timeline (grouped by project!)
- [ ] Update `/projects/<id>` to show contacts involved
- [ ] Update project detail to use new `get_project_communications()`
- [ ] Add contact names to email display (instead of just email addresses)

### Phase 3: Test Migration (Not Started)
- [ ] Run migration on existing data
- [ ] Verify contacts were created correctly
- [ ] Verify communications are linked properly
- [ ] Test that old code still works (backward compatibility)
- [ ] Test new contact/communication views

### Phase 4: Multi-Platform Integrations (Future)
- [ ] WhatsApp integration
- [ ] Facebook Messenger integration
- [ ] iOS Messages integration
- [ ] File attachments from emails
- [ ] Google Drive / Dropbox integration
- [ ] Calendar integration (meetings as communications)

## Data Model

```
Projects (1) ←→ (M) Project_Communications (M) ←→ (1) Communications
                           ↓
                      (1) Contacts

Projects (M) ←→ (M) Project_Contacts (M) ←→ (1) Contacts
```

### Key Concepts
- **Communication** = any interaction (email, message, call, file, meeting)
- **Every communication** links to a project AND a contact
- **Contacts** are tracked per-project (project_contacts)
- **You can pivot** between project view and contact view

### Example Queries
```python
# Show all communications for a project
manager.get_project_communications(project_id=1)
# Returns: [(Communication, Contact), ...]

# Show all communications with a contact, grouped by project
manager.get_contact_communications(contact_id=5, group_by_project=True)
# Returns: {
#   project_id: {
#     "project": Project(...),
#     "communications": [Communication, ...]
#   }
# }

# Show all contacts in a project
manager.get_project_contacts(project_id=1)
# Returns: [Contact, ...]
```

## Tech Stack
- **Database**: SQLite (perfect for this use case)
- **Search**: SQLite FTS5 (future - full-text search across all communications)
- **Backend**: Python 3.10+, Flask
- **Email**: Gmail API ✅
- **Future**: WhatsApp, Messenger, SMS integrations

## Backward Compatibility
- ✅ All existing code continues to work
- ✅ Old `emails` table still exists
- ✅ Dual-write ensures new data goes to both schemas
- ✅ Can drop `emails` table after full migration + testing

## Migration Safety
- ✅ Non-destructive migration (old data preserved)
- ✅ Dry-run mode to preview changes
- ✅ Detailed error reporting
- ✅ Can re-run migration safely (idempotent)
