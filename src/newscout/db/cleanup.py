import sqlite3
from datetime import datetime, timedelta

from newscout.db import core, stories


def clear_all(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("UPDATE fetcher SET running = 0 WHERE id = 1")
        conn.execute("DELETE FROM stories")
        conn.execute("DELETE FROM events")


def _forget(conn: sqlite3.Connection, where: str, params: tuple) -> int:
    hidden = ", ".join(f"'{status}'" for status in stories.HIDDEN)
    with conn:
        count = conn.execute(
            f"UPDATE stories SET status = 'gone', event_id = NULL"
            f" WHERE status NOT IN ({hidden}) AND {where}",
            params,
        ).rowcount
        core.drop_empty_events(conn)
    return count


def delete_older_than(conn: sqlite3.Connection, before: datetime) -> int:
    return _forget(conn, "sort_at < ?", (core.to_text(before),))


def delete_status(conn: sqlite3.Connection, status: str) -> int:
    if status in stories.HIDDEN or status not in stories.RAW_STATUSES:
        raise ValueError(f"Unknown status: {status}")
    return _forget(conn, "status = ?", (status,))


def prune(conn: sqlite3.Connection, now: datetime, trash_days: int, news_days: int) -> None:
    with conn:
        conn.execute(
            """UPDATE stories SET status = 'gone'
               WHERE status IN ('trash', 'dropped') AND fetched_at < ?""",
            (core.to_text(now - timedelta(days=trash_days)),),
        )
        conn.execute(
            "DELETE FROM stories WHERE fetched_at < ?",
            (core.to_text(now - timedelta(days=news_days)),),
        )
        core.drop_empty_events(conn)
