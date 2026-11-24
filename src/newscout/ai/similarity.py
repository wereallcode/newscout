import re
import sqlite3
from datetime import timedelta

from newscout import db
from newscout.models import Event, Story

WINDOW = timedelta(hours=24)
THRESHOLD = 0.2
MAX_CANDIDATES = 5
STEM = 5
STOPWORDS = {"ile", "bir", "için", "olan", "oldu", "gibi", "daha", "the", "and", "for", "with"}


def _words(text: str) -> set[str]:
    text = text.replace("İ", "i").replace("I", "ı").lower()
    words = (word.split("'")[0].split("’")[0] for word in re.findall(r"[\w'’]+", text))
    return {word[:STEM] for word in words if len(word) >= 3 and word not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    left, right = _words(a), _words(b)
    return len(left & right) / len(left | right) if left and right else 0.0


def candidates(conn: sqlite3.Connection, story: Story) -> list[Event]:
    nearby = [
        event
        for event in db.news.recent(conn, since=story.sort_at - WINDOW)
        if abs(event.sort_at - story.sort_at) <= WINDOW
    ]
    scored = sorted(
        (
            (
                max(
                    similarity(story.title, t)
                    for t in (event.title, *[s.title for s in event.sources])
                ),
                event,
            )
            for event in nearby
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [event for score, event in scored[:MAX_CANDIDATES] if score >= THRESHOLD]
