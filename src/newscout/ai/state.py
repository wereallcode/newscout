import sqlite3

from newscout import db

KEY = "deepseek_api_key"
RUNNING = "ai_running"
STATUS = "ai_status"
PROBLEM = "Problem: "


def key(conn: sqlite3.Connection) -> str | None:
    return db.settings.get(conn, KEY)


def save_key(conn: sqlite3.Connection, value: str) -> None:
    db.settings.put(conn, KEY, value)
    report(conn, None)
    set_running(conn, True)


def remove_key(conn: sqlite3.Connection) -> None:
    db.settings.put(conn, KEY, "")
    db.settings.put(conn, STATUS, "")


def running(conn: sqlite3.Connection) -> bool:
    return bool(db.settings.get(conn, RUNNING))


def set_running(conn: sqlite3.Connection, on: bool) -> None:
    db.settings.put(conn, RUNNING, "1" if on else "")


def report(conn: sqlite3.Connection, problem: str | None) -> None:
    db.settings.put(conn, STATUS, f"{PROBLEM}{problem}"[:300] if problem else "ok")


def problem(conn: sqlite3.Connection) -> str | None:
    status = db.settings.get(conn, STATUS) or ""
    return status.removeprefix(PROBLEM) if status.startswith(PROBLEM) else None


def tested(conn: sqlite3.Connection) -> bool:
    return db.settings.get(conn, STATUS) == "ok"
