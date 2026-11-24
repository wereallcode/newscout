import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    relevance TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_checked_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    failures INTEGER NOT NULL DEFAULT 0,
    next_due_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    guid_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    summary TEXT NOT NULL,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    sort_at TEXT NOT NULL,
    event_id INTEGER REFERENCES events(id),
    status TEXT NOT NULL DEFAULT 'waiting',
    relevant INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    UNIQUE (source_id, guid_hash)
);
CREATE INDEX IF NOT EXISTS stories_event ON stories (event_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    sort_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_sort ON events (sort_at DESC);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY,
    value TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kind TEXT NOT NULL DEFAULT 'deepseek',
    model TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS fetcher (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    running INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TEXT,
    last_pass_at TEXT,
    last_pass_added INTEGER NOT NULL DEFAULT 0,
    interval_minutes INTEGER NOT NULL DEFAULT 15
);
INSERT OR IGNORE INTO fetcher (id) VALUES (1);
"""


def default_path() -> Path:
    return Path(os.environ.get("NEWSCOUT_DB", "data/newscout.db"))


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _add_columns(conn)
    return conn


LATER_COLUMNS = {
    "api_keys": {
        "kind": "TEXT NOT NULL DEFAULT 'deepseek'",
        "model": "TEXT NOT NULL DEFAULT ''",
    },
}


def _add_columns(conn: sqlite3.Connection) -> None:
    for table, columns in LATER_COLUMNS.items():
        have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def to_text(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def to_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def drop_empty_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM events WHERE id NOT IN"
        " (SELECT event_id FROM stories WHERE event_id IS NOT NULL)"
    )
