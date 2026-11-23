import sqlite3
from dataclasses import dataclass

from newscout import db

ACTIVE = "ai_active_key"
RUNNING = "ai_running"
STATUS = "ai_status"
PROBLEM = "Problem: "
# Before several keys could be kept, the one key lived in this setting.
LEGACY_KEY = "deepseek_api_key"


class DuplicateKey(Exception):
    pass


@dataclass(frozen=True)
class ApiKey:
    id: int
    hint: str
    added_at: str
    active: bool


def _migrate(conn: sqlite3.Connection) -> None:
    legacy = db.settings.get(conn, LEGACY_KEY)
    if not legacy:
        return
    with conn:
        conn.execute("INSERT OR IGNORE INTO api_keys (value) VALUES (?)", (legacy,))
    row = conn.execute("SELECT id FROM api_keys WHERE value = ?", (legacy,)).fetchone()
    db.settings.put(conn, ACTIVE, str(row[0]))
    db.settings.put(conn, LEGACY_KEY, "")


def _active_id(conn: sqlite3.Connection) -> int | None:
    value = db.settings.get(conn, ACTIVE)
    return int(value) if value and value.isdigit() else None


def keys(conn: sqlite3.Connection) -> list[ApiKey]:
    _migrate(conn)
    active = _active_id(conn)
    rows = conn.execute("SELECT id, value, added_at FROM api_keys ORDER BY id")
    return [ApiKey(row[0], row[1][-4:], row[2][:10], row[0] == active) for row in rows]


def value_of(conn: sqlite3.Connection, key_id: int) -> str | None:
    row = conn.execute("SELECT value FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return row[0] if row else None


def key(conn: sqlite3.Connection) -> str | None:
    _migrate(conn)
    active = _active_id(conn)
    return value_of(conn, active) if active else None


# A new key has just passed its check, so it becomes the one the AI uses.
def add_key(conn: sqlite3.Connection, value: str) -> int:
    _migrate(conn)
    try:
        with conn:
            cursor = conn.execute("INSERT INTO api_keys (value) VALUES (?)", (value,))
    except sqlite3.IntegrityError as error:
        raise DuplicateKey from error
    use_key(conn, cursor.lastrowid, None)
    set_running(conn, True)
    return cursor.lastrowid


def use_key(conn: sqlite3.Connection, key_id: int, problem: str | None) -> None:
    db.settings.put(conn, ACTIVE, str(key_id))
    report(conn, problem)


# Removing the key in use hands over to the newest key left, untested.
def remove_key(conn: sqlite3.Connection, key_id: int) -> None:
    was_active = key_id == _active_id(conn)
    with conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    if not was_active:
        return
    row = conn.execute("SELECT id FROM api_keys ORDER BY id DESC LIMIT 1").fetchone()
    db.settings.put(conn, ACTIVE, str(row[0]) if row else "")
    db.settings.put(conn, STATUS, "")


def running(conn: sqlite3.Connection) -> bool:
    return bool(db.settings.get(conn, RUNNING))


def set_running(conn: sqlite3.Connection, on: bool) -> None:
    db.settings.put(conn, RUNNING, "1" if on else "")


# The status always describes the key in use.
def report(conn: sqlite3.Connection, problem: str | None) -> None:
    db.settings.put(conn, STATUS, f"{PROBLEM}{problem}"[:300] if problem else "ok")


def problem(conn: sqlite3.Connection) -> str | None:
    status = db.settings.get(conn, STATUS) or ""
    return status.removeprefix(PROBLEM) if status.startswith(PROBLEM) else None


def tested(conn: sqlite3.Connection) -> bool:
    return db.settings.get(conn, STATUS) == "ok"
