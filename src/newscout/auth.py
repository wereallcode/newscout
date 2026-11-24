import secrets
import sqlite3
import time

from werkzeug.security import check_password_hash, generate_password_hash

from newscout import db

MIN_LENGTH = 8
FREE_ATTEMPTS = 5
WAIT_SECONDS = 30


class TooManyAttempts(Exception):
    pass


def enabled(conn: sqlite3.Connection) -> bool:
    return bool(db.settings.get(conn, "password"))


def token(conn: sqlite3.Connection) -> str | None:
    return db.settings.get(conn, "session_token")


def secret(conn: sqlite3.Connection) -> str:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('session_secret', ?)",
            (secrets.token_hex(32),),
        )
    return db.settings.get(conn, "session_secret")


def set_password(conn: sqlite3.Connection, password: str) -> None:
    _save(
        conn,
        {"password": generate_password_hash(password), "session_token": secrets.token_hex(16)},
    )


def remove_password(conn: sqlite3.Connection) -> None:
    _save(conn, {})


def verify(conn: sqlite3.Connection, password: str) -> bool:
    _count_attempt(conn)
    if not check_password_hash(db.settings.get(conn, "password") or "", password):
        return False
    _clear(conn, "login_attempts", "login_blocked_until")
    return True


def _save(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM settings WHERE key IN"
            " ('password', 'session_token', 'login_attempts', 'login_blocked_until')"
        )
        conn.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", values.items())


def _clear(conn: sqlite3.Connection, *keys: str) -> None:
    with conn:
        conn.executemany("DELETE FROM settings WHERE key = ?", [(key,) for key in keys])


def _count_attempt(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if time.time() < float(db.settings.get(conn, "login_blocked_until") or 0):
            raise TooManyAttempts
        attempts = int(db.settings.get(conn, "login_attempts") or 0) + 1
        values = {"login_attempts": str(attempts)}
        if attempts >= FREE_ATTEMPTS:
            values["login_blocked_until"] = str(time.time() + WAIT_SECONDS)
        conn.executemany(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", values.items()
        )
