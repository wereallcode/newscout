import sqlite3
from dataclasses import dataclass

from newscout import db


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    hint: str
    default: str


LANGUAGES = ("English", "Turkish", "German", "French", "Spanish")

RELEVANCE = "Keep politics, economy and world news.\nDrop sports, celebrity gossip and advertising."

STEPS = (
    Step(
        "merge",
        "Merge",
        "When two stories are the same news",
        "Merge stories that report the same real-world event, even when their headlines differ.",
    ),
    Step(
        "rewrite",
        "Rewrite",
        "How headlines and descriptions are written",
        "Write a new headline: say plainly what happened, who did what and where.\n"
        "No questions, no teasers, no exaggeration; the headline gives the news away.\n"
        "Write a new description: one or two sentences with the key facts.\n"
        "Write in the news' own language and in a neutral tone.",
    ),
)


def relevance(conn: sqlite3.Connection, source_id: int) -> str:
    return db.groups.relevance_for(conn, source_id).strip() or RELEVANCE


def load(conn: sqlite3.Connection) -> dict[str, str]:
    texts = {step.key: db.settings.get(conn, f"ai_{step.key}") or step.default for step in STEPS}
    return texts | {"language": language(conn)}


def save(conn: sqlite3.Connection, texts: dict[str, str]) -> None:
    for step in STEPS:
        text = texts.get(step.key, "").strip()
        db.settings.put(conn, f"ai_{step.key}", "" if text == step.default else text)


def language(conn: sqlite3.Connection) -> str:
    return db.settings.get(conn, "news_language") or ""


def set_language(conn: sqlite3.Connection, value: str) -> None:
    db.settings.put(conn, "news_language", value if value in LANGUAGES else "")


def in_language(rewrite: str, language: str) -> str:
    if not language:
        return rewrite
    return (
        f"{rewrite}\nWrite the title and summary in {language}, whatever language the sources use."
    )
