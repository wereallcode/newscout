import sqlite3
from datetime import datetime

from newscout.db import core, sources
from newscout.models import FetcherState


def get(conn: sqlite3.Connection) -> FetcherState:
    row = conn.execute("SELECT * FROM fetcher WHERE id = 1").fetchone()
    return FetcherState(
        running=bool(row["running"]),
        heartbeat_at=core.to_time(row["heartbeat_at"]),
        last_pass_at=core.to_time(row["last_pass_at"]),
        last_pass_added=row["last_pass_added"],
    )


def start(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("UPDATE fetcher SET running = 1 WHERE id = 1")
        conn.execute("UPDATE sources SET next_due_at = NULL")


def make_due(conn: sqlite3.Connection, source_id: int | None = None) -> None:
    with conn:
        if source_id is None:
            conn.execute("UPDATE sources SET next_due_at = NULL")
        else:
            conn.execute("UPDATE sources SET next_due_at = NULL WHERE id = ?", (source_id,))


def stop(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("UPDATE fetcher SET running = 0 WHERE id = 1")


def heartbeat(conn: sqlite3.Connection, now: datetime) -> None:
    with conn:
        conn.execute("UPDATE fetcher SET heartbeat_at = ? WHERE id = 1", (core.to_text(now),))


def record_pass(conn: sqlite3.Connection, now: datetime, added: int) -> None:
    with conn:
        conn.execute(
            "UPDATE fetcher SET last_pass_at = ?, last_pass_added = ? WHERE id = 1",
            (core.to_text(now), added),
        )


def next_due(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute(f"SELECT MIN(next_due_at) FROM sources WHERE {sources.ACTIVE}").fetchone()
    return core.to_time(row[0])


def get_interval(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT interval_minutes FROM fetcher WHERE id = 1").fetchone()[0]


def set_interval(conn: sqlite3.Connection, minutes: int) -> None:
    with conn:
        conn.execute("UPDATE fetcher SET interval_minutes = ? WHERE id = 1", (minutes,))
        conn.execute("UPDATE sources SET next_due_at = NULL WHERE failures = 0")
