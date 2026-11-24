import sqlite3
from datetime import datetime, timedelta

from newscout.db import core, sources
from newscout.models import Stats


def latest_id(conn: sqlite3.Connection, table: str) -> int:
    if table not in ("stories", "events"):
        raise ValueError(table)
    return conn.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0]


def count_after(conn: sqlite3.Connection, table: str, row_id: int) -> int:
    if table not in ("stories", "events"):
        raise ValueError(table)
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE id > ?", (row_id,)).fetchone()[0]


def summary(conn: sqlite3.Connection, since: datetime) -> Stats:
    (today,) = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE fetched_at >= ? AND status != 'skipped'",
        (core.to_text(since),),
    ).fetchone()
    active, failing = conn.execute(
        f"""SELECT COUNT(*), COALESCE(SUM(last_error IS NOT NULL), 0)
           FROM sources WHERE {sources.ACTIVE}"""
    ).fetchone()
    return Stats(today, active, failing)


def count_since(conn: sqlite3.Connection, since: datetime) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE fetched_at >= ? AND status != 'skipped'",
        (core.to_text(since),),
    )
    return row.fetchone()[0]


def hourly(conn: sqlite3.Connection, now: datetime, hours: int = 24) -> list[int]:
    start = now - timedelta(hours=hours)
    counts = [0] * hours
    for (fetched,) in conn.execute(
        "SELECT fetched_at FROM stories WHERE fetched_at >= ? AND status != 'skipped'",
        (core.to_text(start),),
    ):
        index = int((datetime.fromisoformat(fetched) - start).total_seconds() // 3600)
        if 0 <= index < hours:
            counts[index] += 1
    return counts


def statuses_since(conn: sqlite3.Connection, since: datetime) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM stories WHERE fetched_at >= ? GROUP BY status",
        (core.to_text(since),),
    )
    return dict(rows.fetchall())


def skipped_since(conn: sqlite3.Connection, since: datetime) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE status = 'skipped' AND fetched_at >= ?",
        (core.to_text(since),),
    )
    return row.fetchone()[0]
