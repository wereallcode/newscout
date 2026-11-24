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
        "Decides when two stories are the same news.",
        "Merge stories that report the same real-world event, even when their headlines differ.",
    ),
    Step(
        "rewrite",
        "Rewrite",
        "Sets how headlines and descriptions are written.",
        "Write a headline that makes people want to read: open with the most striking fact,\n"
        "use strong active verbs and concrete numbers, names and places.\n"
        "The headline states the news: never a question, never a teaser.\n"
        "Stay accurate: every claim must come from the sources, with their exact strength;\n"
        "when the sources hedge (suspected, claims, could), the headline hedges too.\n"
        "Write a one-sentence description with the key facts the headline left out;\n"
        "add context or consequences only when the sources give them.",
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


# The Language setting alone decides the language, so the Rewrite text never has to.
def in_language(rewrite: str, language: str) -> str:
    if not language:
        return f"{rewrite}\nWrite the title and summary in the language of the sources."
    return (
        f"{rewrite}\nWrite the title and summary in {language}, whatever language the sources use."
    )
