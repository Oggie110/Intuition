from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from anthropic import Anthropic

class DigestError(RuntimeError):
    pass


SECTION_RE = re.compile(
    r"^##\s+(?P<header>.+?)\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)
THEME_HEADER_RE = re.compile(r"^Theme:\s*(.+?)\s*$", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*(?:[-*]\s+|\d+\.\s+)(.+?)\s*$")
CITATION_RE = re.compile(r"\[@bm:(\d+)\]")


def _is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _model_name() -> str:
    return os.environ.get("ANTHROPIC_DIGEST_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))


def _default_period() -> tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=7)
    return start.isoformat(), end.isoformat()


def _select_bookmarks(conn: sqlite3.Connection, period_start: str, period_end: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          b.id AS bookmark_id,
          b.url,
          b.author_username,
          b.author_name,
          b.tweet_date,
          e.linked_title AS title,
          COALESCE(e.summary, '') AS summary,
          snippet(bookmark_fts, 0, '<mark>', '</mark>', ' … ', 18) AS snippet
        FROM bookmarks b
        LEFT JOIN enrichments e ON e.bookmark_id = b.id
        LEFT JOIN bookmark_fts ON bookmark_fts.rowid = b.id
        WHERE b.tweet_date >= ? AND b.tweet_date <= ?
        ORDER BY b.tweet_date DESC;
        """.strip(),
        (period_start, period_end),
    ).fetchall()
    return [dict(r) for r in rows]


def _strip_inline_citations(text: str) -> str:
    text = CITATION_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _extract_bullets(body: str) -> list[str]:
    bullets: list[str] = []
    for line in body.splitlines():
        m = BULLET_RE.match(line)
        if m:
            bullets.append(_strip_inline_citations(m.group(1)))
    return bullets


def _extract_summary(body: str) -> str:
    lines = body.splitlines()
    para_lines: list[str] = []
    started = False
    for raw in lines:
        line = raw.strip()
        if not line:
            if started:
                break
            continue
        if BULLET_RE.match(line):
            break
        if line.startswith("#"):
            continue
        para_lines.append(line)
        started = True
    return _strip_inline_citations(" ".join(para_lines))


def parse_digest_markdown(md: str) -> dict[str, Any]:
    themes: list[dict[str, Any]] = []
    overall_takeaways: list[str] = []
    citations: list[dict[str, Any]] = []

    for m in SECTION_RE.finditer(md):
        header = m.group("header").strip()
        body = m.group("body").strip()

        if header.lower() == "overall takeaways":
            overall_takeaways = _extract_bullets(body)
            continue

        hm = THEME_HEADER_RE.match(header)
        if not hm:
            continue

        title = hm.group(1).strip()
        key_takeaways = _extract_bullets(body)
        summary = _extract_summary(body)
        bookmark_ids = sorted({int(x) for x in CITATION_RE.findall(body)})

        themes.append(
            {
                "theme_id": f"theme-{len(themes) + 1}",
                "title": title or f"Theme {len(themes) + 1}",
                "summary": summary,
                "key_takeaways": key_takeaways,
                "bookmark_ids": bookmark_ids,
            }
        )
        for bid in bookmark_ids:
            citations.append({"bookmark_id": bid})

    if not themes:
        # Defensive fallback: derive up to 3 coarse themes from top lines.
        preview_lines = [ln.strip() for ln in md.splitlines() if ln.strip()][:6]
        if preview_lines:
            themes.append(
                {
                    "theme_id": "theme-1",
                    "title": "Weekly highlights",
                    "summary": " ".join(preview_lines[:2]),
                    "key_takeaways": preview_lines[2:5],
                    "bookmark_ids": sorted({int(x) for x in CITATION_RE.findall(md)}),
                }
            )

    return {
        "themes": themes,
        "overall_takeaways": overall_takeaways,
        "citations": citations,
    }


def _resolve_citations(conn: sqlite3.Connection, citation_ids: list[int]) -> list[dict[str, Any]]:
    if not citation_ids:
        return []
    unique_ids = sorted(set(citation_ids))
    placeholders = ",".join("?" for _ in unique_ids)
    rows = conn.execute(
        f"""
        SELECT id AS bookmark_id, url, author_name, author_username, tweet_date
        FROM bookmarks
        WHERE id IN ({placeholders});
        """.strip(),
        tuple(unique_ids),
    ).fetchall()
    by_id = {int(r["bookmark_id"]): dict(r) for r in rows}
    out: list[dict[str, Any]] = []
    for bid in unique_ids:
        row = by_id.get(bid)
        if not row:
            out.append({"bookmark_id": bid})
            continue
        out.append(
            {
                "bookmark_id": bid,
                "url": row.get("url"),
                "title": None,
                "author_name": row.get("author_name"),
                "author_username": row.get("author_username"),
                "tweet_date": row.get("tweet_date"),
            }
        )
    return out


def generate(conn: sqlite3.Connection, *, period_start: Optional[str], period_end: Optional[str]) -> dict[str, Any]:
    if not _is_configured():
        raise DigestError("ANTHROPIC_API_KEY is not set")

    if not period_start or not period_end:
        period_start, period_end = _default_period()

    bms = _select_bookmarks(conn, period_start, period_end)

    system = (
        "You are generating a bookmark digest grounded in provided bookmarks.\n"
        "Return markdown only (no JSON, no code fences).\n"
        "Use this exact structure:\n"
        "# Weekly Digest\n"
        "## Overview\n"
        "<2-4 sentences>\n"
        "## Theme: <title>\n"
        "<summary paragraph with citations>\n"
        "- <takeaway> [@bm:<id>]\n"
        "- <takeaway> [@bm:<id>]\n"
        "(repeat for 3-5 themes)\n"
        "## Overall Takeaways\n"
        "- <takeaway>\n"
        "- <takeaway>\n"
        "Rules:\n"
        "- Cite non-trivial claims using [@bm:<bookmark_id>]\n"
        "- Use only bookmark_ids present in the input\n"
        "- Keep under 700 words\n"
    )

    user = (
        f"Digest period:\nstart={period_start}, end={period_end}\n\n"
        "Bookmarks (authoritative sources):\n"
        f"{json.dumps(bms, ensure_ascii=False)}\n\n"
        "Generate the digest JSON now."
    )

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    markdown = ""
    last_err: Exception | None = None
    token_budgets = [1400, 2200]
    for attempt in range(len(token_budgets)):
        retry_hint = "\n\nPrevious output was invalid. Follow the required markdown structure exactly." if attempt > 0 else ""
        try:
            msg = client.messages.create(
                model=_model_name(),
                max_tokens=token_budgets[attempt],
                system=system,
                messages=[{"role": "user", "content": user + retry_hint}],
            )
        except Exception as e:
            last_err = e
            continue
        if getattr(msg, "stop_reason", None) == "max_tokens":
            last_err = ValueError("Model hit max_tokens before completing JSON")
            continue
        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        markdown = text.strip()
        if markdown:
            break

    if not markdown:
        if last_err and "authentication" in str(last_err).lower():
            raise DigestError("Anthropic authentication failed. Check ANTHROPIC_API_KEY in .env") from last_err
        markdown = "No digest content returned."

    parsed = parse_digest_markdown(markdown)

    # Store digest (markdown is canonical)
    cur = conn.execute(
        "INSERT INTO digests(period_start, period_end, content) VALUES(?, ?, ?);",
        (period_start, period_end, markdown),
    )
    digest_id = int(cur.lastrowid)
    conn.commit()

    citation_ids = [int(c["bookmark_id"]) for c in parsed["citations"] if "bookmark_id" in c]
    resolved_citations = _resolve_citations(conn, citation_ids)

    return {
        "digest": {
            "id": digest_id,
            "period_start": period_start,
            "period_end": period_end,
            "created_at": conn.execute(
                "SELECT created_at FROM digests WHERE id = ?;", (digest_id,)
            ).fetchone()["created_at"],
            "content_markdown": markdown,
            "data": {
                "period": {"start": period_start, "end": period_end},
                "themes": parsed["themes"],
                "overall_takeaways": parsed["overall_takeaways"],
            },
            "citations": resolved_citations,
            "diagnostics": {"markdown_first": True, "theme_count": len(parsed["themes"])},
        }
    }


def list_digests(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, period_start, period_end, created_at FROM digests ORDER BY created_at DESC LIMIT ?;",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_digest(conn: sqlite3.Connection, digest_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        "SELECT id, period_start, period_end, content, created_at FROM digests WHERE id = ?;",
        (digest_id,),
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    parsed = parse_digest_markdown(out.get("content") or "")
    citation_ids = [int(c["bookmark_id"]) for c in parsed["citations"] if "bookmark_id" in c]
    out["data"] = {
        "period": {"start": out.get("period_start"), "end": out.get("period_end")},
        "themes": parsed["themes"],
        "overall_takeaways": parsed["overall_takeaways"],
    }
    out["citations"] = _resolve_citations(conn, citation_ids)
    return out

