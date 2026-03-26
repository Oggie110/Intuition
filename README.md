# Intuition

Local-first Bookmark Intelligence Platform for X/Twitter bookmarks.

## What this is

- **Ingestion**: fetches bookmarks from the local **Bird CLI** (`~/bin/bird`)
- **Storage**: SQLite + FTS5 (no external DB)
- **Enrichment**: optional AI summaries/tags via Anthropic Claude (requires API key)
- **UI**: Next.js dashboard (digest, chat, browse)

## Prereqs

- Python 3.11+
- Node.js 20+
- `pnpm`
- Bird CLI installed locally at `~/bin/bird` and authenticated (`~/.config/bird/credentials`)

## Backend

Create a virtualenv, install deps, run the API:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Environment variables:

- `ANTHROPIC_API_KEY` (optional, required for enrichment/chat/digest generation)

## Web

```bash
cd web
pnpm install
pnpm dev
```

By default, the web app expects the backend at `http://localhost:8000`.

