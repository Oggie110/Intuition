from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EnrichmentJob:
    id: int
    bookmark_id: int
    status: str
    attempts: int


def enqueue_unenriched(conn: sqlite3.Connection, limit: Optional[int] = None) -> int:
    lim_sql = ""
    params: tuple = ()
    if limit is not None:
        lim_sql = " LIMIT ?"
        params = (limit,)

    cur = conn.execute(
        (
            """
            INSERT OR IGNORE INTO enrichment_jobs(bookmark_id, status)
            SELECT b.id, 'pending'
            FROM bookmarks b
            LEFT JOIN enrichments e ON e.bookmark_id = b.id
            WHERE e.bookmark_id IS NULL
            ORDER BY b.tweet_date DESC
            """
            + lim_sql
            + ";"
        ),
        params,
    )
    conn.commit()
    return int(cur.rowcount or 0)


def claim_next_job(conn: sqlite3.Connection, lock_owner: str, lock_ttl_seconds: int = 600) -> Optional[EnrichmentJob]:
    # Atomic "claim" pattern for SQLite: UPDATE using a scalar subquery selecting the next eligible job.
    # Jobs are eligible if:
    # - status pending, or failed with next_attempt_at <= now
    # - not locked, or lock has expired
    cur = conn.execute(
        """
        UPDATE enrichment_jobs
        SET status='processing',
            locked_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            lock_owner=?
        WHERE id = (
          SELECT j.id
          FROM enrichment_jobs j
          WHERE
            (
              j.status='pending'
              OR (j.status='failed' AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= strftime('%Y-%m-%dT%H:%M:%fZ','now')))
            )
            AND (
              j.locked_at IS NULL
              OR j.locked_at <= strftime('%Y-%m-%dT%H:%M:%fZ','now', '-' || ? || ' seconds')
            )
          ORDER BY j.created_at ASC
          LIMIT 1
        )
        RETURNING id, bookmark_id, status, attempts;
        """.strip(),
        (lock_owner, lock_ttl_seconds),
    )
    row = cur.fetchone()
    conn.commit()
    if not row:
        return None
    return EnrichmentJob(
        id=int(row["id"]),
        bookmark_id=int(row["bookmark_id"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
    )


def mark_succeeded(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        """
        UPDATE enrichment_jobs
        SET status='succeeded', last_error=NULL, skip_reason=NULL, locked_at=NULL, lock_owner=NULL
        WHERE id = ?;
        """.strip(),
        (job_id,),
    )
    conn.commit()


def mark_skipped(conn: sqlite3.Connection, job_id: int, reason: str) -> None:
    conn.execute(
        """
        UPDATE enrichment_jobs
        SET status='skipped', skip_reason=?, locked_at=NULL, lock_owner=NULL
        WHERE id = ?;
        """.strip(),
        (reason, job_id),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, job_id: int, error: str, next_attempt_at: Optional[str]) -> None:
    conn.execute(
        """
        UPDATE enrichment_jobs
        SET status='failed',
            attempts=attempts+1,
            last_error=?,
            next_attempt_at=?,
            locked_at=NULL,
            lock_owner=NULL
        WHERE id = ?;
        """.strip(),
        (error, next_attempt_at, job_id),
    )
    conn.commit()

