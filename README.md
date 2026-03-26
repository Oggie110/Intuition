# Intuition

Local-first Bookmark Intelligence Platform for X/Twitter bookmarks.

## What this is

- **Ingestion**: fetches bookmarks from the local **Bird CLI** (`~/bin/bird`)
- **Storage**: SQLite + FTS5 (no external DB)
- **Enrichment**: optional AI summaries/tags via Anthropic Claude (requires API key)
- **UI**: Next.js dashboard (digest, chat, browse)

See **`memory.md`** for ports, proxy behavior, and other notes for ongoing work.

## Prereqs

- Python 3.11+
- Node.js 20+
- `pnpm`
- Bird CLI installed locally at `~/bin/bird` and authenticated (`~/.config/bird/credentials`)

## Backend

Create a virtualenv, install deps, run the API:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010
```

**Environment** (repo root `.env`, loaded on startup; do not commit secrets):

- `ANTHROPIC_API_KEY` — required for enrichment, chat, and digest generation
- Optional: `ANTHROPIC_MODEL`, `ANTHROPIC_CHAT_MODEL`, `ANTHROPIC_DIGEST_MODEL` to override defaults

## Web

```bash
cd web
pnpm install
pnpm dev --port 3010
```

Open `http://127.0.0.1:3010`. The app calls **`/api/proxy/...`** on the Next.js origin; the proxy forwards to the FastAPI backend. By default the proxy targets `http://127.0.0.1:8010`. Override with **`BACKEND_API_BASE`** or **`NEXT_PUBLIC_API_BASE`** in `web/.env.local` if your API runs elsewhere.
