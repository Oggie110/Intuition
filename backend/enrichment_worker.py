from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

import sqlite3

from backend import claude_client
from backend import enrichment_queue
from backend import enrichment_store
from backend import link_extractor


RATE_SECONDS = 6.0  # 10 per minute


@dataclass(frozen=True)
class WorkerResult:
    processed: int
    succeeded: int
    failed: int
    skipped: int


def run_batch(conn: sqlite3.Connection, *, max_items: int = 10, lock_owner: str = "manual") -> WorkerResult:
    processed = succeeded = failed = skipped = 0
    next_allowed = 0.0

    while processed < max_items:
        now = time.monotonic()
        if now < next_allowed:
            time.sleep(max(0.0, next_allowed - now))

        job = enrichment_queue.claim_next_job(conn, lock_owner=lock_owner)
        if not job:
            break

        processed += 1
        ok = _process_job(conn, job)
        if ok == "succeeded":
            succeeded += 1
        elif ok == "skipped":
            skipped += 1
        else:
            failed += 1

        next_allowed = time.monotonic() + RATE_SECONDS

    return WorkerResult(processed=processed, succeeded=succeeded, failed=failed, skipped=skipped)


def _load_bookmark(conn: sqlite3.Connection, bookmark_id: int) -> dict:
    row = conn.execute(
        "SELECT id, tweet_id, author_username, author_name, body, tweet_date, url, media FROM bookmarks WHERE id = ?;",
        (bookmark_id,),
    ).fetchone()
    if not row:
        raise RuntimeError("Bookmark not found")
    media = []
    try:
        media = json.loads(row["media"]) if row["media"] else []
    except Exception:
        media = []
    return {
        "id": int(row["id"]),
        "tweet_id": row["tweet_id"],
        "author_username": row["author_username"],
        "author_name": row["author_name"],
        "body": row["body"],
        "tweet_date": row["tweet_date"],
        "url": row["url"],
        "media": media,
    }


def _process_job(conn: sqlite3.Connection, job: enrichment_queue.EnrichmentJob) -> str:
    try:
        bm = _load_bookmark(conn, job.bookmark_id)

        body = (bm.get("body") or "").strip()
        media = bm.get("media") or []
        if not body and media:
            enrichment_queue.mark_skipped(conn, job.id, "media_only")
            return "skipped"

        link_url = link_extractor.pick_link_url(body)
        linked = link_extractor.fetch_and_extract(link_url) if link_url else link_extractor.LinkedContent(None, None, "")
        bm_payload = {
            **bm,
            "linked_url": linked.linked_url,
            "linked_title": linked.linked_title,
            "linked_content": linked.linked_content,
        }

        if not claude_client.is_configured():
            enrichment_queue.mark_skipped(conn, job.id, "anthropic_not_configured")
            return "skipped"

        res = claude_client.enrich_bookmark(bm_payload)

        conn.execute("BEGIN;")
        enrichment_store.upsert_enrichment(
            conn,
            bookmark_id=job.bookmark_id,
            summary=res.summary,
            key_insights=res.key_insights,
            category=res.category,
            linked_url=linked.linked_url,
            linked_title=linked.linked_title,
            linked_content=linked.linked_content,
        )
        enrichment_store.upsert_tags_and_links(conn, bookmark_id=job.bookmark_id, tags=res.tags)
        conn.commit()

        enrichment_queue.mark_succeeded(conn, job.id)
        return "succeeded"
    except Exception as e:
        # very simple backoff: retry in 30s * attempts (capped)
        attempts_row = conn.execute("SELECT attempts FROM enrichment_jobs WHERE id = ?;", (job.id,)).fetchone()
        attempts = int(attempts_row["attempts"]) if attempts_row else job.attempts
        delay_s = min(300, 30 * max(1, attempts + 1))
        retry_at = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now', '+' || ? || ' seconds') AS t;",
            (delay_s,),
        ).fetchone()["t"]
        enrichment_queue.mark_failed(conn, job.id, str(e), retry_at)
        return "failed"
