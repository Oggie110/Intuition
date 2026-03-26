PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS bookmarks (
  id              INTEGER PRIMARY KEY,
  tweet_id         TEXT    NOT NULL UNIQUE,
  author_username  TEXT    NOT NULL,
  author_name      TEXT    NOT NULL,
  body             TEXT    NOT NULL,
  tweet_date       TEXT    NOT NULL,
  url              TEXT    NOT NULL,
  media            TEXT,
  raw_output        TEXT    NOT NULL,
  created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  is_read           INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0,1)),
  is_archived       INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_tweet_date     ON bookmarks(tweet_date);
CREATE INDEX IF NOT EXISTS idx_bookmarks_author        ON bookmarks(author_username);
CREATE INDEX IF NOT EXISTS idx_bookmarks_created_at    ON bookmarks(created_at);
CREATE INDEX IF NOT EXISTS idx_bookmarks_is_archived   ON bookmarks(is_archived);
CREATE INDEX IF NOT EXISTS idx_bookmarks_is_read       ON bookmarks(is_read);

CREATE TABLE IF NOT EXISTS enrichments (
  id              INTEGER PRIMARY KEY,
  bookmark_id     INTEGER NOT NULL UNIQUE,
  summary         TEXT,
  key_insights    TEXT,
  category        TEXT,
  linked_url      TEXT,
  linked_title    TEXT,
  linked_content  TEXT,
  enriched_at     TEXT   NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_enrichments_enriched_at  ON enrichments(enriched_at);
CREATE INDEX IF NOT EXISTS idx_enrichments_category     ON enrichments(category);

CREATE TABLE IF NOT EXISTS tags (
  id        INTEGER PRIMARY KEY,
  name      TEXT    NOT NULL UNIQUE,
  category  TEXT
);

CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);

CREATE TABLE IF NOT EXISTS bookmark_tags (
  bookmark_id INTEGER NOT NULL,
  tag_id      INTEGER NOT NULL,
  created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (bookmark_id, tag_id),
  FOREIGN KEY (bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id)      REFERENCES tags(id)      ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_bookmark_tags_tag_id ON bookmark_tags(tag_id);

CREATE TABLE IF NOT EXISTS digests (
  id           INTEGER PRIMARY KEY,
  period_start TEXT    NOT NULL,
  period_end   TEXT    NOT NULL,
  content      TEXT    NOT NULL,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_digests_created_at  ON digests(created_at);
CREATE INDEX IF NOT EXISTS idx_digests_period      ON digests(period_start, period_end);

CREATE TABLE IF NOT EXISTS conversations (
  id          TEXT PRIMARY KEY,
  title       TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at);

CREATE TABLE IF NOT EXISTS messages (
  id               TEXT PRIMARY KEY,
  conversation_id  TEXT NOT NULL,
  role             TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  content          TEXT NOT NULL,
  sources          TEXT,
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_time ON messages(conversation_id, created_at);

CREATE TRIGGER IF NOT EXISTS trg_messages_ai_conversation_updated_at
AFTER INSERT ON messages
BEGIN
  UPDATE conversations
  SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE id = NEW.conversation_id;
END;

CREATE VIRTUAL TABLE IF NOT EXISTS bookmark_fts USING fts5(
  body,
  summary,
  linked_content,
  tags,
  author_username,
  author_name,
  linked_title,
  content=''
);

CREATE VIEW IF NOT EXISTS bookmark_fts_source AS
SELECT
  b.id AS bookmark_id,
  b.body AS body,
  COALESCE(e.summary, '') AS summary,
  COALESCE(e.linked_content, '') AS linked_content,
  COALESCE(REPLACE(group_concat(DISTINCT t.name), ',', ' '), '') AS tags,
  b.author_username AS author_username,
  b.author_name AS author_name,
  COALESCE(e.linked_title, '') AS linked_title
FROM bookmarks b
LEFT JOIN enrichments e ON e.bookmark_id = b.id
LEFT JOIN bookmark_tags bt ON bt.bookmark_id = b.id
LEFT JOIN tags t ON t.id = bt.tag_id
GROUP BY b.id;

CREATE TRIGGER IF NOT EXISTS trg_bookmarks_ai_fts_insert
AFTER INSERT ON bookmarks
BEGIN
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bookmarks_ai_fts_update
AFTER UPDATE OF body, author_username, author_name ON bookmarks
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', NEW.id);
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bookmarks_ad_fts_delete
AFTER DELETE ON bookmarks
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', OLD.id);
END;

CREATE TRIGGER IF NOT EXISTS trg_enrichments_ai_fts_insert
AFTER INSERT ON enrichments
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', NEW.bookmark_id);
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = NEW.bookmark_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_enrichments_ai_fts_update
AFTER UPDATE OF summary, linked_content, linked_title ON enrichments
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', NEW.bookmark_id);
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = NEW.bookmark_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_enrichments_ad_fts_delete
AFTER DELETE ON enrichments
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', OLD.bookmark_id);
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = OLD.bookmark_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bookmark_tags_ai_fts_insert
AFTER INSERT ON bookmark_tags
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', NEW.bookmark_id);
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = NEW.bookmark_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_bookmark_tags_ad_fts_delete
AFTER DELETE ON bookmark_tags
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid) VALUES('delete', OLD.bookmark_id);
  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT bookmark_id, body, summary, linked_content, tags, author_username, author_name, linked_title
  FROM bookmark_fts_source
  WHERE bookmark_id = OLD.bookmark_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_tags_au_fts_update
AFTER UPDATE OF name, category ON tags
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid)
  SELECT DISTINCT 'delete', bt.bookmark_id
  FROM bookmark_tags bt
  WHERE bt.tag_id = NEW.id;

  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT s.bookmark_id, s.body, s.summary, s.linked_content, s.tags, s.author_username, s.author_name, s.linked_title
  FROM bookmark_fts_source s
  WHERE s.bookmark_id IN (
    SELECT DISTINCT bt2.bookmark_id
    FROM bookmark_tags bt2
    WHERE bt2.tag_id = NEW.id
  );
END;

CREATE TRIGGER IF NOT EXISTS trg_tags_ad_fts_delete
AFTER DELETE ON tags
BEGIN
  INSERT INTO bookmark_fts(bookmark_fts, rowid)
  SELECT DISTINCT 'delete', bt.bookmark_id
  FROM bookmark_tags bt
  WHERE bt.tag_id = OLD.id;

  INSERT INTO bookmark_fts(rowid, body, summary, linked_content, tags, author_username, author_name, linked_title)
  SELECT s.bookmark_id, s.body, s.summary, s.linked_content, s.tags, s.author_username, s.author_name, s.linked_title
  FROM bookmark_fts_source s
  WHERE s.bookmark_id IN (
    SELECT DISTINCT bt2.bookmark_id
    FROM bookmark_tags bt2
    WHERE bt2.tag_id = OLD.id
  );
END;

COMMIT;

