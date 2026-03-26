PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS enrichment_jobs (
  id INTEGER PRIMARY KEY,
  bookmark_id INTEGER NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK (status IN ('pending','processing','succeeded','failed','skipped')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error TEXT,
  skip_reason TEXT,
  locked_at TEXT,
  lock_owner TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_status_next ON enrichment_jobs(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_locked_at ON enrichment_jobs(locked_at);

CREATE TRIGGER IF NOT EXISTS trg_enrichment_jobs_au_updated_at
AFTER UPDATE ON enrichment_jobs
BEGIN
  UPDATE enrichment_jobs
  SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE id = NEW.id;
END;

COMMIT;

