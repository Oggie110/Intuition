from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False)
    conn.execute(
        "INSERT INTO app_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
        (key, encoded),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[Any]:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?;", (key,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]

