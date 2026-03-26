from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Iterable

from backend.bird_client import ParsedBookmark


def insert_bookmarks(conn: sqlite3.Connection, bookmarks: Iterable[ParsedBookmark]) -> tuple[int, int, int]:
    bookmarks_list = list(bookmarks)
    fetched = len(bookmarks_list)
    stored = 0
    skipped = 0

    for bm in bookmarks_list:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO bookmarks(
              tweet_id, author_username, author_name, body, tweet_date, url, media, raw_output
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """.strip(),
            (
                bm.tweet_id,
                bm.author_username,
                bm.author_name,
                bm.body,
                bm.tweet_date,
                bm.url,
                json.dumps(bm.media, ensure_ascii=False),
                bm.raw_output,
            ),
        )
        if cur.rowcount == 1:
            stored += 1
        else:
            skipped += 1

    conn.commit()
    return fetched, stored, skipped

