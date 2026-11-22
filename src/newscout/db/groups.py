import sqlite3

from newscout.db import core, sources
from newscout.models import Group

DEFAULT_NAME = "My sources"


class DuplicateGroup(Exception):
    pass


def add(conn: sqlite3.Connection, name: str, relevance: str = "") -> int:
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO groups (name, relevance) VALUES (?, ?)", (name, relevance)
            )
    except sqlite3.IntegrityError as error:
        raise DuplicateGroup(name) from error
    return cursor.lastrowid


def default(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM groups WHERE name = ?", (DEFAULT_NAME,)).fetchone()
    return row[0] if row else add(conn, DEFAULT_NAME)


def list_all(conn: sqlite3.Connection) -> list[Group]:
    members: dict[int, list] = {}
    for source in sources.list_all(conn):
        members.setdefault(source.group_id, []).append(source)
    rows = conn.execute("SELECT * FROM groups ORDER BY name COLLATE NOCASE")
    return [
        Group(
            row["id"],
            row["name"],
            bool(row["enabled"]),
            row["relevance"],
            members.get(row["id"], []),
        )
        for row in rows
    ]


def get(conn: sqlite3.Connection, group_id: int) -> Group | None:
    return next((group for group in list_all(conn) if group.id == group_id), None)


def update(conn: sqlite3.Connection, group_id: int, name: str, relevance: str) -> None:
    try:
        with conn:
            conn.execute(
                "UPDATE groups SET name = ?, relevance = ? WHERE id = ?",
                (name, relevance, group_id),
            )
    except sqlite3.IntegrityError as error:
        raise DuplicateGroup(name) from error


def set_enabled(conn: sqlite3.Connection, group_id: int, enabled: bool) -> None:
    with conn:
        conn.execute("UPDATE groups SET enabled = ? WHERE id = ?", (int(enabled), group_id))


def delete(conn: sqlite3.Connection, group_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        core.drop_empty_events(conn)


def relevance_for(conn: sqlite3.Connection, source_id: int) -> str:
    row = conn.execute(
        "SELECT relevance FROM groups JOIN sources ON sources.group_id = groups.id"
        " WHERE sources.id = ?",
        (source_id,),
    ).fetchone()
    return row[0] if row else ""
