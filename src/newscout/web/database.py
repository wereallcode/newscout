import sqlite3

from flask import current_app, g

from newscout import db


def conn() -> sqlite3.Connection:
    if "conn" not in g:
        g.conn = db.connect(current_app.config["DATABASE"])
    return g.conn


def close(_error: BaseException | None) -> None:
    connection = g.pop("conn", None)
    if connection is not None:
        connection.close()
