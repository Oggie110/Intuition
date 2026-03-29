# Intuition — project memory

Persistent notes for humans and agents working in this repo. Update when architecture, ports, or workflows change.

## Purpose

**Intuition** is a local-first “bookmark intelligence” app: ingest X/Twitter bookmarks via the **Bird CLI**, store them in **SQLite + FTS5**, optionally **enrich** with Anthropic Claude, then **search**, **chat (RAG)**, and generate **weekly-style digests** from the Next.js UI.

## Repository layout

| Area | Path |
|------|------|
| FastAPI backend | `backend/` |
| SQL migrations | `backend/migrations/` |
| SQLite DB (default) | `data/intuition.db` (gitignored under `data/`) |
| Next.js app | `web/` |
| Digest home route | `web/app/page.tsx` (server shell) → `digest-home-entry.tsx` (client `dynamic`, `ssr: false`) → `home-client.tsx` (dashboard UI) |
| Product requirements | `tasks/prd-bookmark-intelligence.md` |
| Cursor rule: styled selects | `.cursor/rules/styled-dropdowns.mdc` |

## How to run (typical dev)

**Backend** (from repo root, venv activated):

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010
```

**Frontend**:

```bash
cd web && pnpm dev --port 3010
```

Open `http://127.0.0.1:3010`. The browser calls **`/api/proxy/...`** only (`web/lib/api.ts`). The Next.js route `web/app/api/proxy/[...path]/route.ts` forwards to the real API; set **`BACKEND_API_BASE`** or **`NEXT_PUBLIC_API_BASE`** (e.g. in `web/.env.local`) to `http://127.0.0.1:8010` if your backend is not on the default host/port.

**One-command startup**:

```bash
make dev-up
```

This starts backend (`:8010`) and frontend (`:3010`) together from repo root.

## Environment

- **Repo-root `.env`** is loaded by the backend on startup (`python-dotenv`, `override=True` so file values win over stale shell env).
- **Do not commit secrets.** `.gitignore` excludes `.env` and `data/`.
- Common variables: `ANTHROPIC_API_KEY`; model overrides such as `ANTHROPIC_MODEL`, `ANTHROPIC_CHAT_MODEL`, `ANTHROPIC_DIGEST_MODEL` (e.g. Sonnet-class models for enrichment, chat, digest).
- Hardening variables: `INTUITION_API_KEY` (requires `x-api-key` on all `/api/*` routes), `INTUITION_EXPOSE_SYSTEM_INFO=true` (shows local paths in `/api/status`; default is redacted).
- Bird CLI is expected at **`~/bin/bird`** with credentials under `~/.config/bird/` as in the PRD.

## Architecture shortcuts

- **Import:** `POST /api/import` runs Bird, parses bookmark blocks, inserts rows, optionally enqueues enrichment jobs.
- **Enrichment:** queue in SQLite; worker batches link fetch + Claude JSON (with JSON repair / fallbacks in `backend/json_utils.py`).
- **Search:** FTS5 with `bm25` where possible; `LIKE` fallback if FTS query fails.
- **Chat:** RAG over bookmarks + conversation persistence; `conversation_id` can be stored client-side (e.g. `localStorage`) and history loaded via `GET /api/conversations/{id}/messages`.
- **Digests:** **markdown-first** generation from Claude; Python parses themes/citations from markdown; citations like `[@bm:ID]` are resolved to URLs for the UI; frontend renders markdown with clickable links.

## Remote

Default remote: `origin` → `https://github.com/Oggie110/Intuition.git` (verify with `git remote -v` if this drifts).

## When editing UI

Match the existing editorial palette (`globals.css` tokens) and follow `.cursor/rules/styled-dropdowns.mdc` for `<select>` styling.

Base `h1`–`h3` rules in `globals.css` use extra line-height so **Syne** extrabold headings do not clip descenders (e.g. `g`).
