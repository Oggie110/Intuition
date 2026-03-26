from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from typing import Any, Optional

from anthropic import Anthropic

from backend.json_utils import parse_json_object, repair_json_with_model


class ChatError(RuntimeError):
    pass


BM_CITE_RE = re.compile(r"\[@bm:(\d+)\]")


def _model_name() -> str:
    return os.environ.get("ANTHROPIC_CHAT_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))


def _is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _build_fts_query(text: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+", text.lower())
    terms = [t for t in terms if len(t) > 1][:10]
    if not terms:
        return ""
    # Prefix matching with OR keeps retrieval tolerant for natural-language prompts.
    return " OR ".join(f"{t}*" for t in terms)


def _ensure_conversation(conn: sqlite3.Connection, conversation_id: Optional[str]) -> str:
    if conversation_id:
        row = conn.execute("SELECT id FROM conversations WHERE id = ?;", (conversation_id,)).fetchone()
        if row:
            return conversation_id
    cid = f"conv_{uuid.uuid4().hex}"
    conn.execute("INSERT INTO conversations(id, title) VALUES(?, NULL);", (cid,))
    conn.commit()
    return cid


def _append_message(conn: sqlite3.Connection, conversation_id: str, role: str, content: str, sources: Any = None) -> None:
    mid = f"msg_{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO messages(id, conversation_id, role, content, sources) VALUES(?, ?, ?, ?, ?);",
        (mid, conversation_id, role, content, json.dumps(sources, ensure_ascii=False) if sources is not None else None),
    )
    conn.commit()


def _last_messages(conn: sqlite3.Connection, conversation_id: str, limit: int = 5) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT ?;
        """.strip(),
        (conversation_id, limit),
    ).fetchall()
    msgs = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    return msgs


def _retrieve_sources(conn: sqlite3.Connection, q: str, limit: int = 10) -> list[dict[str, Any]]:
    fts_q = _build_fts_query(q)
    if fts_q:
        try:
            rows = conn.execute(
                """
                WITH hits AS (
                  SELECT rowid AS bookmark_id,
                         bm25(bookmark_fts, 5.0, 3.0, 1.5, 2.0, 1.0, 1.0, 2.0) AS score,
                         snippet(bookmark_fts, 1, '<mark>', '</mark>', ' … ', 12) AS snippet_summary,
                         snippet(bookmark_fts, 0, '<mark>', '</mark>', ' … ', 12) AS snippet_body
                  FROM bookmark_fts
                  WHERE bookmark_fts MATCH ?
                  ORDER BY score ASC
                  LIMIT ?
                )
                SELECT
                  b.id AS bookmark_id,
                  b.url,
                  b.author_username,
                  b.author_name,
                  b.tweet_date,
                  b.body AS body,
                  COALESCE(e.summary, '') AS summary,
                  e.linked_title AS title,
                  COALESCE(NULLIF(h.snippet_summary, ''), h.snippet_body) AS snippet
                FROM hits h
                JOIN bookmarks b ON b.id = h.bookmark_id
                LEFT JOIN enrichments e ON e.bookmark_id = b.id;
                """.strip(),
                (fts_q, limit),
            ).fetchall()
            out = [dict(r) for r in rows]
            if out:
                return out
        except sqlite3.OperationalError:
            pass

    # Fallback retrieval when FTS query parsing fails or returns nothing.
    like_q = f"%{q.strip()}%"
    rows = conn.execute(
        """
        SELECT
          b.id AS bookmark_id,
          b.url,
          b.author_username,
          b.author_name,
          b.tweet_date,
          b.body AS body,
          COALESCE(e.summary, '') AS summary,
          e.linked_title AS title,
          substr(COALESCE(e.summary, b.body), 1, 220) AS snippet
        FROM bookmarks b
        LEFT JOIN enrichments e ON e.bookmark_id = b.id
        WHERE b.body LIKE ? OR COALESCE(e.summary, '') LIKE ?
        ORDER BY b.tweet_date DESC
        LIMIT ?;
        """.strip(),
        (like_q, like_q, limit),
    ).fetchall()
    out = [dict(r) for r in rows]
    if out:
        return out

    rows = conn.execute(
        """
        SELECT
          b.id AS bookmark_id,
          b.url,
          b.author_username,
          b.author_name,
          b.tweet_date,
          b.body AS body,
          COALESCE(e.summary, '') AS summary,
          e.linked_title AS title,
          substr(COALESCE(e.summary, b.body), 1, 220) AS snippet
        FROM bookmarks b
        LEFT JOIN enrichments e ON e.bookmark_id = b.id
        ORDER BY b.tweet_date DESC
        LIMIT ?;
        """.strip(),
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def chat(conn: sqlite3.Connection, *, message: str, conversation_id: Optional[str]) -> dict[str, Any]:
    cid = _ensure_conversation(conn, conversation_id)
    _append_message(conn, cid, "user", message)

    retrieved = _retrieve_sources(conn, message, limit=10)
    context_messages = _last_messages(conn, cid, limit=5)

    if not _is_configured():
        raise ChatError("ANTHROPIC_API_KEY is not set")

    system = (
        "You are Intuition’s bookmark-grounded assistant.\n\n"
        "You MUST answer using only the provided retrieved_bookmarks for factual claims about what the user saved.\n"
        "If information is missing, say so and suggest what to look up next.\n\n"
        "IMPORTANT CONTEXT QUALITY RULE:\n"
        "- Each retrieved bookmark may include full tweet body text in `body` and optional enrichment text in `summary`.\n"
        "- If retrieved_bookmarks is non-empty, do NOT claim there is no accessible text unless body/summary are actually empty across all retrieved bookmarks.\n\n"
        "CITATIONS (strict):\n"
        "- Every non-trivial claim that relies on retrieved_bookmarks MUST include an inline citation marker in the markdown as [@bm:<bookmark_id>].\n"
        "- Do NOT invent bookmarks. Do NOT cite IDs that are not present in retrieved_bookmarks.\n\n"
        "OUTPUT (strict JSON only, no surrounding markdown, no extra prose):\n"
        "Return exactly one JSON object matching this shape:\n"
        "{\n"
        '  "type": "chat_rag_response",\n'
        '  "markdown": "...",\n'
        '  "data": {\n'
        '    "answer": "optional",\n'
        '    "follow_up_questions": ["..."],\n'
        '    "actions": [{"label":"...", "rationale":"...", "bookmark_ids":[123]}]\n'
        "  },\n"
        '  "citations": [\n'
        '    {"bookmark_id":123,"url":"...","title":null,"author_name":"...","author_username":"...","tweet_date":"..."}\n'
        "  ]\n"
        "}\n"
    )

    user = (
        f"User query:\n{message}\n\n"
        "Conversation context (most recent last):\n"
        f"{json.dumps(context_messages, ensure_ascii=False)}\n\n"
        "Retrieved bookmarks (authoritative sources):\n"
        f"{json.dumps(retrieved, ensure_ascii=False)}\n\n"
        "Now produce the required JSON response.\n"
        "If retrieved_bookmarks has entries with body/summary text, synthesize from that text directly."
    )

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    data = None
    last_err: Exception | None = None
    last_text = ""
    for attempt in range(2):
        retry_hint = (
            "\n\nIMPORTANT: Your previous response was not valid JSON. Return ONLY one valid JSON object."
            if attempt == 1
            else ""
        )
        try:
            msg = client.messages.create(
                model=_model_name(),
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": user + retry_hint}],
            )
        except Exception as e:
            last_err = e
            continue

        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        text = text.strip()
        last_text = text
        try:
            data = parse_json_object(text)
            break
        except Exception as e:
            last_err = e

    if data is None and last_text:
        try:
            data = repair_json_with_model(client, model=_model_name(), raw_text=last_text)
        except Exception as e:
            last_err = e

    if data is None:
        if last_err and "authentication" in str(last_err).lower():
            raise ChatError("Anthropic authentication failed. Check ANTHROPIC_API_KEY in .env") from last_err
        raise ChatError("Claude did not return valid JSON") from last_err

    markdown = str(data.get("markdown") or "").strip()
    citations = data.get("citations") or []
    if not markdown:
        raise ChatError("Missing markdown in response")

    # Persist assistant message with sources
    _append_message(conn, cid, "assistant", markdown, sources=citations)

    # Basic sanity: ensure cited ids are subset of retrieved ids
    retrieved_ids = {int(r["bookmark_id"]) for r in retrieved if "bookmark_id" in r}
    cited_ids = {int(x) for x in BM_CITE_RE.findall(markdown)}
    bad = sorted([i for i in cited_ids if i not in retrieved_ids])
    if bad:
        # still return, but include a warning for debugging
        data.setdefault("data", {})
        data["data"]["warning"] = f"Model cited unknown bookmark ids: {bad}"

    return {"conversation_id": cid, "answer_markdown": markdown, "sources": citations, "raw": data}


def get_conversation_messages(conn: sqlite3.Connection, conversation_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT role, content, sources, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC;
        """.strip(),
        (conversation_id,),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        sources = []
        try:
            sources = json.loads(r["sources"]) if r["sources"] else []
        except Exception:
            sources = []
        out.append(
            {
                "role": r["role"],
                "content": r["content"],
                "sources": sources,
                "created_at": r["created_at"],
            }
        )
    return out

