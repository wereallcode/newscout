import hashlib
import sqlite3
from datetime import datetime

from newscout.db import core, sources
from newscout.models import Entry, Story

RAW_STATUSES = ("waiting", "kept", "merged", "dropped", "trash", "skipped", "gone")
HIDDEN = ("skipped", "gone")


def save(
    conn: sqlite3.Connection,
    source_id: int,
    entries: list[Entry],
    now: datetime,
    fresh_since: datetime | None = None,
) -> int:
    if sources.get(conn, source_id) is None:
        return 0
    rows = []
    for entry in entries:
        stale = bool(fresh_since and entry.published_at and entry.published_at < fresh_since)
        rows.append(
            (
                source_id,
                hashlib.sha256(entry.guid.encode()).hexdigest(),
                entry.title,
                entry.link,
                entry.summary,
                core.to_text(entry.published_at),
                core.to_text(now),
                core.to_text(min(entry.published_at or now, now)),
                "skipped" if stale else "waiting",
                None,
            )
        )
    try:
        with conn:
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO stories (source_id, guid_hash, title, link, summary,
                   published_at, fetched_at, sort_at, status, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            return conn.total_changes - before
    except sqlite3.IntegrityError:
        return 0


def from_row(row: sqlite3.Row) -> Story:
    return Story(
        id=row["id"],
        source_id=row["source_id"],
        source_name=row["source_name"],
        title=row["title"],
        link=row["link"],
        summary=row["summary"],
        published_at=core.to_time(row["published_at"]),
        fetched_at=core.to_time(row["fetched_at"]),
        sort_at=core.to_time(row["sort_at"]),
        status=row["status"],
        reason=row["reason"],
        event_id=row["event_id"],
        relevant=bool(row["relevant"]),
    )


SELECT = """SELECT stories.*, sources.name AS source_name FROM stories
             JOIN sources ON sources.id = stories.source_id"""


def list_raw(
    conn: sqlite3.Connection, limit: int = 50, offset: int = 0, statuses: tuple[str, ...] = ()
) -> list[Story]:
    placeholders = ", ".join("?" * len(statuses))
    where = (
        f" WHERE status IN ({placeholders})"
        if statuses
        else f" WHERE status NOT IN ({', '.join(repr(s) for s in HIDDEN)})"
    )
    rows = conn.execute(
        SELECT + where + " ORDER BY sort_at DESC, stories.id DESC LIMIT ? OFFSET ?",
        [*statuses, limit, offset],
    )
    return [from_row(row) for row in rows]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return dict(conn.execute("SELECT status, COUNT(*) FROM stories GROUP BY status"))


def get(conn: sqlite3.Connection, story_id: int) -> Story | None:
    row = conn.execute(SELECT + " WHERE stories.id = ?", (story_id,)).fetchone()
    return from_row(row) if row else None


def waiting(conn: sqlite3.Connection, limit: int) -> list[Story]:
    rows = conn.execute(
        SELECT + " WHERE status = 'waiting' ORDER BY sort_at, stories.id LIMIT ?", (limit,)
    )
    return [from_row(row) for row in rows]


def set_status(
    conn: sqlite3.Connection, story_id: int, status: str, reason: str | None = None
) -> None:
    if status not in RAW_STATUSES:
        raise ValueError(f"Unknown status: {status}")
    with conn:
        conn.execute(
            "UPDATE stories SET status = ?, reason = ?, event_id = NULL WHERE id = ?",
            (status, reason, story_id),
        )
        core.drop_empty_events(conn)


def mark_relevant(conn: sqlite3.Connection, story_id: int) -> None:
    with conn:
        conn.execute("UPDATE stories SET relevant = 1 WHERE id = ?", (story_id,))


def restore(conn: sqlite3.Connection, story_id: int) -> None:
    set_status(conn, story_id, "waiting")
    mark_relevant(conn, story_id)


def keep(conn: sqlite3.Connection, story_id: int, title: str, summary: str) -> int:
    with conn:
        sort_at = conn.execute("SELECT sort_at FROM stories WHERE id = ?", (story_id,)).fetchone()
        event_id = conn.execute(
            "INSERT INTO events (title, summary, sort_at) VALUES (?, ?, ?)",
            (title, summary, sort_at[0]),
        ).lastrowid
        conn.execute(
            "UPDATE stories SET status = 'kept', reason = NULL, event_id = ? WHERE id = ?",
            (event_id, story_id),
        )
    return event_id


def attach(
    conn: sqlite3.Connection, story_id: int, event_id: int, title: str, summary: str
) -> None:
    with conn:
        conn.execute(
            "UPDATE stories SET status = 'merged', reason = NULL, event_id = ? WHERE id = ?",
            (event_id, story_id),
        )
        conn.execute(
            """UPDATE events SET title = ?, summary = ?,
               sort_at = (SELECT MAX(sort_at) FROM stories WHERE event_id = ?) WHERE id = ?""",
            (title, summary, event_id, event_id),
        )
