import sqlite3
from dataclasses import dataclass

from newscout import db
from newscout.ai.deepseek import DeepSeekJudge
from newscout.ai.local import LocalJudge

ACTIVE = "ai_active_key"
RUNNING = "ai_running"
STATUS = "ai_status"
PROBLEM = "Problem: "
# Before several keys could be kept, the one key lived in this setting.
LEGACY_KEY = "deepseek_api_key"


class DuplicateKey(Exception):
    pass


# One way for the AI to write: a DeepSeek key, or a model on a local server.
@dataclass(frozen=True)
class ApiKey:
    id: int
    kind: str
    value: str
    model: str
    added_at: str
    active: bool

    @property
    def local(self) -> bool:
        return self.kind == "local"

    @property
    def url(self) -> str:
        return self.value.removesuffix(f"#{self.model}")

    @property
    def name(self) -> str:
        return self.model if self.local else "DeepSeek"

    @property
    def hint(self) -> str:
        """What tells entries apart: the server for a model, the last digits for a key."""
        if self.local:
            return self.url.removeprefix("http://").removesuffix("/v1")
        return self.value[-4:]

    def judge(self) -> DeepSeekJudge:
        return LocalJudge(self.url, self.model) if self.local else DeepSeekJudge(self.value)


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
    rows = conn.execute("SELECT id, kind, value, model, added_at FROM api_keys ORDER BY id")
    return [ApiKey(*row[:4], row[4][:10], row[0] == active) for row in rows]


def get(conn: sqlite3.Connection, key_id: int) -> ApiKey | None:
    return next((item for item in keys(conn) if item.id == key_id), None)


def active(conn: sqlite3.Connection) -> ApiKey | None:
    return next((item for item in keys(conn) if item.active), None)


def key(conn: sqlite3.Connection) -> str | None:
    """The DeepSeek key in use, or None when the AI uses a local model."""
    item = active(conn)
    return item.value if item and not item.local else None


# A new entry has just passed its check, so it becomes the one the AI uses.
def add_key(conn: sqlite3.Connection, value: str, kind: str = "deepseek", model: str = "") -> int:
    _migrate(conn)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO api_keys (value, kind, model) VALUES (?, ?, ?)", (value, kind, model)
            )
    except sqlite3.IntegrityError as error:
        raise DuplicateKey from error
    use_key(conn, cursor.lastrowid, None)
    set_running(conn, True)
    return cursor.lastrowid


def add_local(conn: sqlite3.Connection, url: str, model: str) -> int:
    return add_key(conn, f"{url}#{model}", "local", model)


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


def judge(conn: sqlite3.Connection) -> DeepSeekJudge | None:
    """The AI that writes the news, or None until a key or a local model is added."""
    item = active(conn)
    return item.judge() if item else None
