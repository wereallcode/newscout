import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from newscout.db import core, groups
from newscout.models import Source


class DuplicateSource(Exception):
    pass


# A source is fetched only while it and its group are both switched on.
ACTIVE = "enabled = 1 AND group_id IN (SELECT id FROM groups WHERE enabled = 1)"


def _from_row(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        group_id=row["group_id"],
        type=row["type"],
        name=row["name"],
        url=row["url"],
        enabled=bool(row["enabled"]),
        last_checked_at=core.to_time(row["last_checked_at"]),
        last_success_at=core.to_time(row["last_success_at"]),
        last_error=row["last_error"],
        failures=row["failures"],
        next_due_at=core.to_time(row["next_due_at"]),
    )


def host(url: str) -> str:
    return urlparse(url).hostname or url


def add(
    conn: sqlite3.Connection,
    url: str,
    type: str = "rss",
    name: str | None = None,
    group_id: int | None = None,
) -> int:
    group_id = group_id or groups.default(conn)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO sources (group_id, type, name, url) VALUES (?, ?, ?, ?)",
                (group_id, type, name or host(url), url),
            )
    except sqlite3.IntegrityError as error:
        raise DuplicateSource(url) from error
    return cursor.lastrowid


def list_all(conn: sqlite3.Connection) -> list[Source]:
    rows = conn.execute("SELECT * FROM sources ORDER BY name COLLATE NOCASE")
    return [_from_row(row) for row in rows]


def get(conn: sqlite3.Connection, source_id: int) -> Source | None:
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return _from_row(row) if row else None


def set_enabled(conn: sqlite3.Connection, source_id: int, enabled: bool) -> None:
    with conn:
        conn.execute("UPDATE sources SET enabled = ? WHERE id = ?", (int(enabled), source_id))


def delete(conn: sqlite3.Connection, source_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        core.drop_empty_events(conn)


def due(conn: sqlite3.Connection, now: datetime) -> list[Source]:
    rows = conn.execute(
        f"SELECT * FROM sources WHERE {ACTIVE} AND (next_due_at IS NULL OR next_due_at <= ?)",
        (core.to_text(now),),
    )
    return [_from_row(row) for row in rows]


def record_success(
    conn: sqlite3.Connection,
    source_id: int,
    now: datetime,
    next_due_at: datetime,
    name: str | None,
) -> None:
    with conn:
        conn.execute(
            """UPDATE sources SET last_checked_at = ?, last_success_at = ?, last_error = NULL,
               failures = 0, next_due_at = ?, name = COALESCE(?, name) WHERE id = ?""",
            (core.to_text(now), core.to_text(now), core.to_text(next_due_at), name, source_id),
        )


def record_failure(
    conn: sqlite3.Connection, source_id: int, now: datetime, next_due_at: datetime, error: str
) -> None:
    with conn:
        conn.execute(
            """UPDATE sources SET last_checked_at = ?, last_error = ?, failures = failures + 1,
               next_due_at = ? WHERE id = ?""",
            (core.to_text(now), error, core.to_text(next_due_at), source_id),
        )
