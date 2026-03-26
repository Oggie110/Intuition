from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Optional


def _build_fts_query(text: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+", text.lower())
    terms = [t for t in terms if len(t) > 1][:10]
    if not terms:
        return ""
    return " OR ".join(f"{t}*" for t in terms)


def search(
    conn: sqlite3.Connection,
    *,
    q: str,
    limit: int = 20,
    offset: int = 0,
    tag: Optional[str] = None,
    author: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    enriched: Optional[bool] = None,
) -> dict[str, Any]:
    fts_q = _build_fts_query(q)
    params: dict[str, Any] = {
        "q": fts_q or q,
        "limit": limit,
        "offset": offset,
        "tag": tag or "",
        "author": author or "",
        "category": category or "",
        "date_from": date_from or "",
        "date_to": date_to or "",
        "enriched": None if enriched is None else (1 if enriched else 0),
        "hl_start": "<mark>",
        "hl_end": "</mark>",
        "ellipsis": " … ",
        "snippet_tokens": 12,
    }

    sql = """
    WITH hits AS (
      SELECT
        rowid AS bookmark_id,
        bm25(
          bookmark_fts,
          5.0, 3.0, 1.5, 2.0, 1.0, 1.0, 2.0
        ) AS score,
        snippet(bookmark_fts, 1, :hl_start, :hl_end, :ellipsis, :snippet_tokens) AS snippet_summary,
        snippet(bookmark_fts, 0, :hl_start, :hl_end, :ellipsis, :snippet_tokens) AS snippet_body
      FROM bookmark_fts
      WHERE bookmark_fts MATCH :q
    )
    SELECT
      b.id,
      b.tweet_id,
      b.author_username,
      b.author_name,
      b.body,
      b.tweet_date,
      b.url,
      b.media,
      b.created_at,
      b.is_read,
      b.is_archived,
      e.summary,
      e.key_insights,
      e.category,
      e.linked_url,
      e.linked_title,
      e.enriched_at,
      hits.score AS relevance_score,
      COALESCE(NULLIF(hits.snippet_summary, ''), hits.snippet_body) AS snippet,
      COALESCE((
        SELECT group_concat(DISTINCT t2.name)
        FROM bookmark_tags bt2
        JOIN tags t2 ON t2.id = bt2.tag_id
        WHERE bt2.bookmark_id = b.id
      ), '') AS tags
    FROM hits
    JOIN bookmarks b ON b.id = hits.bookmark_id
    LEFT JOIN enrichments e ON e.bookmark_id = b.id
    WHERE
      (:author = '' OR b.author_username = :author OR b.author_name LIKE '%' || :author || '%')
      AND (:category = '' OR e.category = :category)
      AND (:date_from = '' OR b.tweet_date >= :date_from)
      AND (:date_to = '' OR b.tweet_date <= :date_to)
      AND (
        :enriched IS NULL
        OR (:enriched = 1 AND e.bookmark_id IS NOT NULL)
        OR (:enriched = 0 AND e.bookmark_id IS NULL)
      )
      AND (:tag = '' OR EXISTS (
        SELECT 1
        FROM bookmark_tags bt2
        JOIN tags t2 ON t2.id = bt2.tag_id
        WHERE bt2.bookmark_id = b.id AND t2.name = :tag
      ))
    ORDER BY hits.score ASC, b.tweet_date DESC
    LIMIT :limit OFFSET :offset;
    """.strip()
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        like_q = f"%{q.strip()}%"
        rows = conn.execute(
            """
            SELECT
              b.id,
              b.tweet_id,
              b.author_username,
              b.author_name,
              b.body,
              b.tweet_date,
              b.url,
              b.media,
              b.created_at,
              b.is_read,
              b.is_archived,
              e.summary,
              e.key_insights,
              e.category,
              e.linked_url,
              e.linked_title,
              e.enriched_at,
              0.0 AS relevance_score,
              substr(COALESCE(e.summary, b.body), 1, 220) AS snippet,
              COALESCE((
                SELECT group_concat(DISTINCT t2.name)
                FROM bookmark_tags bt2
                JOIN tags t2 ON t2.id = bt2.tag_id
                WHERE bt2.bookmark_id = b.id
              ), '') AS tags
            FROM bookmarks b
            LEFT JOIN enrichments e ON e.bookmark_id = b.id
            WHERE
              (b.body LIKE ? OR COALESCE(e.summary, '') LIKE ? OR COALESCE(e.linked_content, '') LIKE ?)
              AND (? = '' OR b.author_username = ? OR b.author_name LIKE '%' || ? || '%')
              AND (? = '' OR e.category = ?)
              AND (? = '' OR b.tweet_date >= ?)
              AND (? = '' OR b.tweet_date <= ?)
            ORDER BY b.tweet_date DESC
            LIMIT ? OFFSET ?;
            """.strip(),
            (
                like_q,
                like_q,
                like_q,
                author or "",
                author or "",
                author or "",
                category or "",
                category or "",
                date_from or "",
                date_from or "",
                date_to or "",
                date_to or "",
                limit,
                offset,
            ),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        media = []
        try:
            media = json.loads(r["media"]) if r["media"] else []
        except Exception:
            media = []

        tags_list = [t for t in (r["tags"] or "").split(",") if t]
        enrichment_obj = None
        if r["summary"] is not None or r["enriched_at"] is not None:
            key_insights = []
            try:
                key_insights = json.loads(r["key_insights"]) if r["key_insights"] else []
            except Exception:
                key_insights = []
            enrichment_obj = {
                "summary": r["summary"],
                "key_insights": key_insights,
                "category": r["category"],
                "linked_url": r["linked_url"],
                "linked_title": r["linked_title"],
                "enriched_at": r["enriched_at"],
                "tags": [{"name": t, "category": None} for t in tags_list],
            }

        results.append(
            {
                "bookmark": {
                    "id": r["id"],
                    "tweet_id": r["tweet_id"],
                    "author_username": r["author_username"],
                    "author_name": r["author_name"],
                    "body": r["body"],
                    "tweet_date": r["tweet_date"],
                    "url": r["url"],
                    "media": media,
                    "created_at": r["created_at"],
                    "is_read": bool(r["is_read"]),
                    "is_archived": bool(r["is_archived"]),
                    "enrichment": enrichment_obj,
                },
                "match": {"snippet": r["snippet"]},
                "score": float(r["relevance_score"]),
            }
        )

    return {"results": results}

