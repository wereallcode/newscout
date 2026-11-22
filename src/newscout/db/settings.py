import sqlite3

DEFAULTS = {"fresh_minutes": "60", "new_minutes": "30", "trash_days": "7", "news_days": "30"}


def get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else DEFAULTS.get(key)


def put(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        if value:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
