import sqlite3
from datetime import datetime

from newscout.db import core, stories
from newscout.models import Event, Story


def _with_sources(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[Event]:
    ids = [row["id"] for row in rows]
    members: dict[int, list[Story]] = {event_id: [] for event_id in ids}
    if ids:
        placeholders = ", ".join("?" * len(ids))
        for row in conn.execute(
            stories.SELECT + f" WHERE event_id IN ({placeholders}) ORDER BY sort_at, stories.id",
            ids,
        ):
            members[row["event_id"]].append(stories.from_row(row))
    return [
        Event(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            sort_at=core.to_time(row["sort_at"]),
            sources=members[row["id"]],
        )
        for row in rows
    ]


def list_page(conn: sqlite3.Connection, limit: int = 50, offset: int = 0) -> list[Event]:
    rows = conn.execute(
        "SELECT * FROM events ORDER BY sort_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)
    )
    return _with_sources(conn, rows.fetchall())


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def trash(conn: sqlite3.Connection, event_id: int) -> None:
    with conn:
        conn.execute(
            """UPDATE stories SET status = 'trash', reason = 'Trashed by you', event_id = NULL
               WHERE event_id = ?""",
            (event_id,),
        )
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


def get(conn: sqlite3.Connection, event_id: int) -> Event | None:
    rows = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchall()
    return _with_sources(conn, rows)[0] if rows else None


def recent(conn: sqlite3.Connection, since: datetime) -> list[Event]:
    rows = conn.execute("SELECT * FROM events WHERE sort_at >= ?", (core.to_text(since),))
    return _with_sources(conn, rows.fetchall())
