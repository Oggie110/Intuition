PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS app_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TRIGGER IF NOT EXISTS trg_app_meta_au_updated_at
AFTER UPDATE ON app_meta
BEGIN
  UPDATE app_meta SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE key = NEW.key;
END;

COMMIT;

