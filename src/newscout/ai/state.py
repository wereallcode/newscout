import sqlite3
from dataclasses import dataclass

from newscout import db
from newscout.ai import local
from newscout.ai.chat import ChatJudge, Check
from newscout.ai.deepseek import DeepSeekJudge, check_key

ACTIVE = "ai_active_key"
RUNNING = "ai_running"
STATUS = "ai_status"
PROBLEM = "Problem: "
LEGACY_KEY = "deepseek_api_key"


class AlreadyAdded(Exception):
    pass


@dataclass(frozen=True)
class Provider:
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
        if self.local:
            return self.url.removeprefix("http://").removesuffix("/v1")
        return "…" + self.value[-4:]

    def judge(self) -> ChatJudge:
        return local.LocalJudge(self.url, self.model) if self.local else DeepSeekJudge(self.value)

    def check(self) -> Check:
        return local.check_model(self.url, self.model) if self.local else check_key(self.value)


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


def providers(conn: sqlite3.Connection) -> list[Provider]:
    _migrate(conn)
    active = _active_id(conn)
    rows = conn.execute("SELECT id, kind, value, model, added_at FROM api_keys ORDER BY id")
    return [Provider(*row[:4], row[4][:10], row[0] == active) for row in rows]


def provider(conn: sqlite3.Connection, provider_id: int) -> Provider | None:
    return next((item for item in providers(conn) if item.id == provider_id), None)


def in_use(conn: sqlite3.Connection) -> Provider | None:
    return next((item for item in providers(conn) if item.active), None)


def add_key(conn: sqlite3.Connection, value: str, kind: str = "deepseek", model: str = "") -> int:
    _migrate(conn)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO api_keys (value, kind, model) VALUES (?, ?, ?)", (value, kind, model)
            )
    except sqlite3.IntegrityError as error:
        raise AlreadyAdded from error
    use(conn, cursor.lastrowid, None)
    set_running(conn, True)
    return cursor.lastrowid


def add_local(conn: sqlite3.Connection, url: str, model: str) -> int:
    return add_key(conn, f"{url}#{model}", "local", model)


def use(conn: sqlite3.Connection, provider_id: int, problem: str | None) -> None:
    db.settings.put(conn, ACTIVE, str(provider_id))
    report(conn, problem)


def remove(conn: sqlite3.Connection, provider_id: int) -> None:
    was_active = provider_id == _active_id(conn)
    with conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (provider_id,))
    if not was_active:
        return
    row = conn.execute("SELECT id FROM api_keys ORDER BY id DESC LIMIT 1").fetchone()
    db.settings.put(conn, ACTIVE, str(row[0]) if row else "")
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


def health(conn: sqlite3.Connection) -> str:
    return "ok" if tested(conn) else "problem" if problem(conn) else "unknown"


def judge(conn: sqlite3.Connection) -> ChatJudge | None:
    item = in_use(conn)
    return item.judge() if item else None
