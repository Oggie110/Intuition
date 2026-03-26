# PRD: Intuition — Bookmark Intelligence Platform

## 1. Introduction

Intuition turns your X/Twitter bookmarks into a searchable, AI-enriched knowledge base. Most people bookmark tweets and never look at them again — the signal is there but it's buried and unsearchable.

Intuition solves this by: ingesting bookmarks automatically, enriching them with AI (summaries, tags, linked content extraction), and surfacing insights through a chat interface and periodic digests.

**Bird CLI** (`~/bin/bird`) handles X bookmark fetching. It's already configured on the developer's machine with credentials at `~/.config/bird/credentials`. The app wraps this existing tool — no X API keys needed.

### Bird CLI Reference

- **Binary**: `~/bin/bird`
- **Credentials**: `~/.config/bird/credentials` (auth token)
- **Commands**:
  - `bird whoami` → `🙋 @username (Display Name)`
  - `bird bookmarks -n 50` → returns bookmarks separated by `──────────────────────────────────────────────────`
- **Tweet block format**:
  ```
  @username (Display Name):
  Tweet body text here...
  🎬 https://pbs.twimg.com/media/... (optional media)
  🖼️ https://pbs.twimg.com/media/... (optional image)
  ┌─ QT @quoted_user:              (optional quote tweet)
  │ Quoted text
  └─ https://x.com/quoted_user/status/123
  📅 Thu Mar 26 03:52:14 +0000 2026
  🔗 https://x.com/username/status/123456789
  ```
- **Parsed fields**: tweet_id, author_username, author_name, body, date, url, media[], raw_output
- **Note**: bird CLI is a local binary, not a package. Users need it installed separately.

---

## 2. Goals

1. **Zero-friction ingestion** — bookmarks flow in automatically or with one click, no manual export
2. **Enriched, searchable archive** — every bookmark gets AI summary, tags, and linked content extracted
3. **Weekly digest** — surface themes, clusters, and actionable insights from recent bookmarks
4. **Conversational retrieval** — ask questions about your bookmark archive in natural language
5. **Lean and portable** — SQLite, no Docker, no external services beyond Claude API

---

## 3. User Stories

### 3.1 Database Schema
**As a developer, I want a SQLite schema for bookmarks and enrichments, so data is stored locally with no external dependencies.**

Acceptance criteria:
- SQLite database with tables: `bookmarks`, `enrichments`, `tags`, `digests`
- `bookmarks` stores: id, tweet_id (unique), author_username, author_name, body, tweet_date, url, media (JSON), raw_output, created_at, is_read, is_archived
- `enrichments` stores: bookmark_id (FK), summary, key_insights (JSON array), linked_url, linked_content, linked_title, enriched_at
- `tags` stores: id, name (unique), category (e.g. "topic", "technology", "person")
- `bookmark_tags` join table: bookmark_id, tag_id
- `digests` stores: id, period_start, period_end, content (markdown), created_at
- FTS5 virtual table over bookmarks.body + enrichments.summary + enrichments.linked_content for full-text search
- Migration system (simple version-based, one .sql file per migration)

### 3.2 Bird CLI Integration
**As a user, I want to fetch my latest X bookmarks with one action, so my archive stays current.**

Acceptance criteria:
- Python module wraps bird CLI (`~/bin/bird bookmarks -n {limit}`)
- Parses bird output format (separator-delimited tweet blocks)
- Deduplicates by tweet_id before inserting
- Returns count: fetched, stored, skipped
- Handles bird CLI not installed (clear error message)
- Handles bird CLI timeout (60s)
- Status check endpoint: `GET /api/status` returns bird availability + last fetch time

### 3.3 Bookmark Enrichment Pipeline
**As a user, I want each bookmark automatically enriched with AI analysis, so I can search and browse by meaning, not just keywords.**

Acceptance criteria:
- After ingestion, queue unenriched bookmarks for processing
- For each bookmark:
  1. If tweet contains a URL → fetch the linked page content (strip HTML, extract article text, limit to 5000 chars)
  2. Send tweet text + linked content to Claude API
  3. Claude returns: 2-3 sentence summary, list of key insights, 3-5 topic tags, category (dev-tools, music, business, research, misc)
  4. Store enrichment + tags in database
  5. Update FTS5 index
- Rate limit: process max 10 bookmarks per minute (respect Claude API limits)
- Skip enrichment for bookmarks that are just media with no text
- Enrichment is idempotent — re-running doesn't create duplicates

### 3.4 Search API
**As a user, I want to search my bookmarks by meaning, so I can find relevant content even if I don't remember exact words.**

Acceptance criteria:
- `GET /api/search?q={query}` returns matching bookmarks with enrichments
- Uses FTS5 for text matching (body + summary + linked_content + tags)
- Results ranked by relevance
- Returns: bookmark data + enrichment + matching snippet
- Supports filters: `tag`, `author`, `date_from`, `date_to`, `category`
- Pagination with limit/offset

### 3.5 Chat Interface (Backend)
**As a user, I want to ask questions about my bookmarks and get AI-powered answers with sources.**

Acceptance criteria:
- `POST /api/chat` accepts `{ message: string, conversation_id?: string }`
- Searches bookmarks relevant to the question (top 10 by FTS5 relevance)
- Sends question + bookmark context to Claude
- Claude answers citing specific bookmarks (by title/author/url)
- Returns: answer text, source bookmarks (id + url + title), conversation_id
- Conversation history stored in `conversations` / `messages` tables
- Context window: include last 5 messages from conversation

### 3.6 Weekly Digest Generation
**As a user, I want a weekly summary of my bookmarks grouped by theme, so I can see patterns and act on insights.**

Acceptance criteria:
- Scheduled or on-demand: `POST /api/digest/generate` with optional `period_start`/`period_end`
- Collects all bookmarks from the period (default: last 7 days)
- Sends to Claude with prompt: "Group these bookmarks by theme, summarize each cluster, highlight actionable insights, note connections to older bookmarks"
- Output structure:
  - Total count + date range
  - Theme clusters (name, bookmark count, summary, key takeaway)
  - "You keep bookmarking about X — here's a synthesis" (for recurring topics)
  - Connected insights: links between this week and older bookmarks
- Stored in `digests` table as markdown
- `GET /api/digests` returns list, `GET /api/digests/{id}` returns full content

### 3.7 Dashboard — Digest View
**As a user, I want a visual dashboard showing my bookmark digest, so I can quickly see what I've been saving and why it matters.**

Acceptance criteria:
- Main dashboard page shows latest digest
- Header: date range, total bookmarks count
- Theme clusters as cards: title, count badge, summary text, expand to see individual bookmarks
- Each bookmark shows: author avatar/initials, tweet text (truncated), tags, enrichment summary
- "Recurring themes" section highlighting topics that appear across multiple weeks
- Click any bookmark → opens tweet URL in new tab
- Fetch button to trigger new bookmark import
- Generate digest button
- Clean, editorial design (inspired by Kazen's dashboard aesthetic)

### 3.8 Dashboard — Chat View
**As a user, I want a chat interface in the dashboard to query my bookmarks conversationally.**

Acceptance criteria:
- Chat panel (full page or sidebar)
- Message input with Enter to send
- AI responses render as markdown with clickable bookmark citations
- Source bookmarks shown as cards below the answer
- Conversation persists across page reloads (stored in DB)
- New conversation button
- Example prompts shown on empty state: "What are the best Claude Code tips?", "Summarize everything about MCP servers", "What music production tools have I bookmarked?"

### 3.9 Dashboard — Browse View
**As a user, I want to browse all my bookmarks with filtering and search, so I can explore my archive.**

Acceptance criteria:
- Grid/list of all bookmarks, newest first
- Search bar (uses FTS5)
- Filter by: tag, category, author, date range, enriched/not-enriched
- Each card shows: author, tweet text, tags, summary, date
- Click to expand → full enrichment, linked content preview, media
- Bulk actions: archive, re-enrich

---

## 4. Functional Requirements

### Ingestion
- Bird CLI wrapper: fetch bookmarks, parse output, store in SQLite
- Deduplication by tweet_id
- Auto-fetch on configurable schedule (default: every 6 hours) OR manual trigger
- Import existing bookmarks from Kazen database (one-time migration script)

### Enrichment
- Claude API integration (Anthropic SDK)
- Link content extraction (HTTP fetch + HTML-to-text)
- Tag generation and categorization
- FTS5 index maintenance
- Background processing queue (simple in-process, no Celery/Redis)

### Search & Chat
- FTS5 full-text search with ranking
- RAG pipeline: search → context assembly → Claude → response with citations
- Conversation persistence

### Digest
- On-demand or scheduled generation
- Theme clustering via Claude
- Cross-week pattern detection
- Markdown output stored in DB

---

## 5. Non-Goals

- **No user accounts / auth** — single-user app for now
- **No real-time streaming** — digests and enrichments run as batch jobs
- **No browser extension** — bird CLI is the only ingestion method for MVP
- **No embedding vectors** — FTS5 is sufficient for MVP search; add vectors later if needed
- **No mobile app** — web dashboard only
- **No X API direct integration** — bird CLI handles this
- **No multi-source ingestion yet** — designed for it but X-only for MVP

---

## 6. Design Considerations

- **Editorial aesthetic** — clean typography, generous whitespace, inspired by Kazen's dashboard-v2 design system (Syne font, hard shadows, yellow accent #ffc845, black borders)
- **Dashboard-first** — the digest view is the landing page, not a settings screen
- **Progressive disclosure** — digest summary → expand cluster → see individual bookmarks → click to source
- **Dark mode** — not for MVP, but don't use colors that make it hard to add later
- **Responsive** — works on desktop, usable on tablet, not optimized for mobile

---

## 7. Technical Considerations

### Stack
- **Backend**: Python 3.11+, FastAPI, SQLite (via sqlite3 stdlib), no ORM (raw SQL is fine for this scale)
- **Frontend**: Next.js 14+, TypeScript, Tailwind CSS, no component library
- **AI**: Anthropic Claude API (claude-sonnet-4-6 for enrichment, claude-sonnet-4-6 for chat)
- **Search**: SQLite FTS5
- **Link extraction**: `httpx` + `beautifulsoup4` for fetching/parsing linked content

### Architecture
```
intuition/
  backend/
    main.py              # FastAPI app
    db.py                # SQLite connection + migrations
    migrations/          # SQL migration files
    bird_client.py       # Bird CLI wrapper (from Kazen's twitter_client.py)
    enrichment.py        # Claude enrichment pipeline
    search.py            # FTS5 search
    chat.py              # RAG chat
    digest.py            # Digest generation
    link_extractor.py    # Fetch and parse linked URLs
  web/
    app/                 # Next.js app router
      page.tsx           # Dashboard — digest view
      chat/page.tsx      # Chat view
      browse/page.tsx    # Browse/search view
    components/
      bookmark-card.tsx
      digest-view.tsx
      chat-panel.tsx
      search-bar.tsx
    lib/
      api.ts             # API client
  data/
    intuition.db         # SQLite database (gitignored)
  .env                   # ANTHROPIC_API_KEY
```

### Bird CLI
- Binary at `~/bin/bird`, credentials at `~/.config/bird/credentials`
- No installation needed if already set up for Kazen
- The `bird_client.py` module is adapted from Kazen's `twitter_client.py` — same parsing logic, stripped of Kazen-specific imports

### Key Dependencies
- `fastapi` + `uvicorn` — API server
- `anthropic` — Claude API
- `httpx` — HTTP client for link extraction
- `beautifulsoup4` — HTML parsing
- `pnpm` — frontend package manager

### Migration from Kazen
- One-time script: read Kazen's Postgres `communications` table where `comm_type = 'x_bookmark'`
- Map fields to Intuition's `bookmarks` table
- Run enrichment pipeline on imported bookmarks
- Requires Kazen's Postgres to be running (Docker)

---

## 8. Success Metrics

1. **Ingestion works** — can fetch 100+ bookmarks and store without errors
2. **Enrichment quality** — summaries are useful, tags are accurate, linked content is captured
3. **Search relevance** — "Claude Code tips" returns Claude Code bookmarks, not random matches
4. **Chat usefulness** — can ask "what are the best dev setup tips I've bookmarked?" and get a good answer with sources
5. **Digest value** — weekly digest surfaces themes you didn't consciously notice
6. **Speed** — dashboard loads in <1s, search returns in <500ms, chat responds in <5s

---

## 9. Open Questions

1. **Scheduling** — should auto-fetch run as a background thread in the FastAPI process, or a separate cron job? (Leaning: background thread like Kazen's email scheduler)
2. **Linked content depth** — should we follow links in tweets that link to other tweets (thread unrolling)? Or just external URLs?
3. **Tag taxonomy** — should tags be free-form from Claude, or constrained to a predefined list that grows over time?
4. **Digest frequency** — weekly is the default, but should daily be an option?
5. **Rename the repo?** — "Intuition" is the old Kazen codename. Keep it or rename to something bookmark-specific?
6. **Cost** — Claude API costs for enriching 1000+ bookmarks. Estimate ~$2-5 for initial enrichment, pennies per week ongoing. Acceptable?
