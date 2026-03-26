from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from backend import bird_client
from backend import bookmark_store
from backend import db as db_mod
from backend import enrichment_queue
from backend import enrichment_worker
from backend import meta
from backend import search as search_mod
from backend import chat as chat_mod
from backend import digest as digest_mod

app = FastAPI(title="Intuition API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3010",
        "http://127.0.0.1:3010",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CONN = None
_CONFIG = None


@app.on_event("startup")
def _startup() -> None:
    global _CONN, _CONFIG
    repo_root = db_mod.repo_root_from_env()
    load_dotenv(dotenv_path=repo_root / ".env", override=True)
    _CONFIG = db_mod.default_config(repo_root)
    _CONN = db_mod.connect(_CONFIG.db_path)
    db_mod.run_migrations(_CONN, _CONFIG.migrations_dir)


@app.get("/api/status")
def status() -> dict:
    db_path = str(_CONFIG.db_path) if _CONFIG else str(Path("data") / "intuition.db")
    bird_path = str(bird_client.default_bird_path())
    bird_installed = bird_client.is_installed()

    who = None
    if bird_installed:
        try:
            ident = bird_client.whoami()
            who = {"username": ident.username, "display_name": ident.display_name}
        except Exception:
            who = None

    last_import_at = meta.get_meta(_CONN, "last_import_at") if _CONN else None
    last_import_result = meta.get_meta(_CONN, "last_import_result") if _CONN else None

    return {
        "ok": True,
        "db": {"path": db_path},
        "bird": {
            "installed": bird_installed,
            "path": bird_path,
            "available": bool(who) if bird_installed else False,
            "whoami": who,
        },
        "imports": {"last_import_at": last_import_at, "last_import_result": last_import_result},
    }


class ImportRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    enqueue_enrichment: bool = True


@app.post("/api/import")
def import_bookmarks(req: ImportRequest) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    if not bird_client.is_installed():
        raise HTTPException(status_code=400, detail="Bird CLI not installed at ~/bin/bird")

    try:
        raw = bird_client.fetch_bookmarks_raw(limit=req.limit)
        parsed = bird_client.parse_bookmarks(raw)
        fetched, stored, skipped = bookmark_store.insert_bookmarks(_CONN, parsed)
    except bird_client.BirdError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    result = {"fetched": fetched, "stored": stored, "skipped": skipped}
    meta.set_meta(_CONN, "last_import_result", result)
    now_row = _CONN.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now') AS now;").fetchone()
    meta.set_meta(_CONN, "last_import_at", now_row["now"] if now_row else None)
    enqueued = 0
    if req.enqueue_enrichment:
        enqueued = enrichment_queue.enqueue_unenriched(_CONN, limit=None)
    return {"ok": True, "result": result, "enqueued_for_enrichment": enqueued}


class EnrichRunRequest(BaseModel):
    max_items: int = Field(default=10, ge=1, le=100)


@app.post("/api/enrich/run")
def enrich_run(req: EnrichRunRequest) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    res = enrichment_worker.run_batch(_CONN, max_items=req.max_items, lock_owner="api")
    return {"ok": True, "result": res.__dict__}


@app.get("/api/search")
def search(
    q: str,
    limit: int = 20,
    offset: int = 0,
    tag: str | None = None,
    author: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    enriched: bool | None = None,
) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    if not q:
        raise HTTPException(status_code=400, detail="Missing q")
    data = search_mod.search(
        _CONN,
        q=q,
        limit=min(max(limit, 1), 100),
        offset=max(offset, 0),
        tag=tag,
        author=author,
        category=category,
        date_from=date_from,
        date_to=date_to,
        enriched=enriched,
    )
    return {"ok": True, "query": q, "pagination": {"limit": limit, "offset": offset}, **data}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Missing message")
    try:
        out = chat_mod.chat(_CONN, message=req.message, conversation_id=req.conversation_id)
    except chat_mod.ChatError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "ok": True,
        "conversation_id": out["conversation_id"],
        "answer_markdown": out["answer_markdown"],
        "sources": out["sources"],
    }


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    rows = chat_mod.get_conversation_messages(_CONN, conversation_id=conversation_id)
    return {"ok": True, "conversation_id": conversation_id, "messages": rows}


class DigestGenerateRequest(BaseModel):
    period_start: str | None = None
    period_end: str | None = None


@app.post("/api/digest/generate")
def digest_generate(req: DigestGenerateRequest) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    try:
        out = digest_mod.generate(_CONN, period_start=req.period_start, period_end=req.period_end)
    except digest_mod.DigestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **out}


@app.get("/api/digests")
def digests(limit: int = 50) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return {"ok": True, "digests": digest_mod.list_digests(_CONN, limit=min(max(limit, 1), 200))}


@app.get("/api/digests/{digest_id}")
def digest_get(digest_id: int) -> dict:
    if _CONN is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    d = digest_mod.get_digest(_CONN, digest_id)
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")
    return {"ok": True, "digest": d}

