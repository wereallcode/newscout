import logging
import sqlite3
from dataclasses import dataclass
from typing import Protocol

from newscout import db
from newscout.ai.instructions import in_language, relevance
from newscout.ai.similarity import candidates
from newscout.models import Event, Story

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Verdict:
    relevant: bool
    reason: str | None = None


@dataclass(frozen=True)
class Draft:
    title: str
    summary: str


class Judge(Protocol):
    def relevant(self, story: Story, instructions: str) -> Verdict: ...

    def match(self, story: Story, candidates: list[Event], instructions: str) -> int | None: ...

    def rewrite(self, stories: list[Story], instructions: str) -> Draft: ...


def handle(
    conn: sqlite3.Connection, judge: Judge, instructions: dict[str, str], story: Story
) -> None:
    # Each finished step is saved, so after a failure the story resumes where it stopped.
    if not story.relevant:
        verdict = judge.relevant(story, relevance(conn, story.source_id))
        if not verdict.relevant:
            db.stories.set_status(conn, story.id, "dropped", verdict.reason or "Not relevant")
            log.info("dropped: %s", story.title)
            return
        db.stories.mark_relevant(conn, story.id)
    options = candidates(conn, story)
    match = judge.match(story, options, instructions["merge"]) if options else None
    target = next((event for event in options if event.id == match), None)
    rewrite = in_language(instructions["rewrite"], instructions.get("language", ""))
    draft = judge.rewrite([*target.sources, story] if target else [story], rewrite)
    if target:
        db.stories.attach(conn, story.id, target.id, draft.title, draft.summary)
        log.info("merged into #%d: %s", target.id, story.title)
    else:
        db.stories.keep(conn, story.id, draft.title, draft.summary)
        log.info("new: %s", story.title)


def process(
    conn: sqlite3.Connection, judge: Judge, instructions: dict[str, str], limit: int = 5
) -> int:
    waiting = db.stories.waiting(conn, limit)
    for story in waiting:
        handle(conn, judge, instructions, story)
    return len(waiting)
