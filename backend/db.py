from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DbConfig:
    db_path: Path
    migrations_dir: Path


def default_config(repo_root: Path) -> DbConfig:
    return DbConfig(
        db_path=repo_root / "data" / "intuition.db",
        migrations_dir=repo_root / "backend" / "migrations",
    )


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """.strip()
    )


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    _ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations;").fetchall()
    return {str(r["version"]) for r in rows}


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[str]:
    migrations_dir.mkdir(parents=True, exist_ok=True)

    applied = _applied_versions(conn)
    migration_files = sorted(
        [
            p
            for p in migrations_dir.glob("*.sql")
            if p.is_file() and not p.name.startswith(".")
        ],
        key=lambda p: p.name,
    )

    newly_applied: list[str] = []
    for path in migration_files:
        version = path.name
        if version in applied:
            continue

        sql = path.read_text(encoding="utf-8")
        # executescript wraps statements in its own implicit transaction unless BEGIN/COMMIT are present
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?);", (version,))
        conn.commit()
        newly_applied.append(version)

    return newly_applied


def repo_root_from_env() -> Path:
    # default: assume backend/ is directly under repo root
    here = Path(__file__).resolve()
    return Path(os.environ.get("INTUITION_REPO_ROOT", str(here.parents[1]))).resolve()

