from __future__ import annotations

import json
import sqlite3


def upsert_enrichment(
    conn: sqlite3.Connection,
    *,
    bookmark_id: int,
    summary: str,
    key_insights: list[str],
    category: str,
    linked_url: str | None,
    linked_title: str | None,
    linked_content: str,
) -> None:
    conn.execute(
        """
        INSERT INTO enrichments(
          bookmark_id, summary, key_insights, category, linked_url, linked_title, linked_content
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(bookmark_id) DO UPDATE SET
          summary=excluded.summary,
          key_insights=excluded.key_insights,
          category=excluded.category,
          linked_url=excluded.linked_url,
          linked_title=excluded.linked_title,
          linked_content=excluded.linked_content,
          enriched_at=strftime('%Y-%m-%dT%H:%M:%fZ','now');
        """.strip(),
        (
            bookmark_id,
            summary,
            json.dumps(key_insights, ensure_ascii=False),
            category,
            linked_url,
            linked_title,
            linked_content,
        ),
    )


def upsert_tags_and_links(
    conn: sqlite3.Connection,
    *,
    bookmark_id: int,
    tags: list[dict[str, str]],
) -> None:
    for t in tags:
        name = (t.get("name") or "").strip()
        kind = (t.get("kind") or "").strip() or None
        if not name:
            continue
        conn.execute(
            "INSERT INTO tags(name, category) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET category=excluded.category;",
            (name, kind),
        )
        tag_id_row = conn.execute("SELECT id FROM tags WHERE name = ?;", (name,)).fetchone()
        if not tag_id_row:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO bookmark_tags(bookmark_id, tag_id) VALUES(?, ?);",
            (bookmark_id, int(tag_id_row["id"])),
        )

