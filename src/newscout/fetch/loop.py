import logging
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime, timedelta
from pathlib import Path

from newscout import db
from newscout.fetch.collectors import COLLECTORS, Collector
from newscout.fetch.steps import STEPS, Step, apply
from newscout.models import FeedResult, Source

MAX_DELAY = timedelta(hours=6)
RETRY_DELAY = 5.0
PRUNE_EVERY = timedelta(hours=1)

log = logging.getLogger(__name__)


def next_due(now: datetime, interval_minutes: int, failures: int) -> datetime:
    delay = timedelta(minutes=interval_minutes) * 2 ** min(failures, 16)
    return now + min(delay, MAX_DELAY)


def _fetch(source: Source, collectors: dict[str, Collector]) -> FeedResult:
    collector = collectors.get(source.type)
    if collector is None:
        raise ValueError("Unknown source type")
    return collector.fetch(source)


def _fail(conn: sqlite3.Connection, source: Source, now: datetime, error: str) -> None:
    log.warning("%s failed: %s", source.url, error)
    due = next_due(now, db.fetcher.get_interval(conn), source.failures + 1)
    db.sources.record_failure(conn, source.id, now, due, error[:300])


def run_pass(
    conn: sqlite3.Connection,
    now: datetime,
    collectors: dict[str, Collector] = COLLECTORS,
    steps: list[Step] = STEPS,
    timeout: float = 25.0,
    workers: int = 8,
    fresh_since: datetime | None = None,
) -> int | None:
    sources = db.sources.due(conn, now)
    if not sources:
        return None
    total = 0
    # Not a context manager: leaving it would wait for a hung fetch.
    pool = ThreadPoolExecutor(max_workers=workers)
    jobs: dict[Future, Source] = {pool.submit(_fetch, s, collectors): s for s in sources}
    done, _ = wait(jobs, timeout=timeout)
    pool.shutdown(wait=False, cancel_futures=True)
    for job, source in jobs.items():
        if job not in done:
            _fail(conn, source, now, "Timed out")
            continue
        try:
            result = job.result()
        except Exception as error:
            _fail(conn, source, now, str(error) or type(error).__name__)
            continue
        entries = [e for e in (apply(entry, steps) for entry in result.entries) if e]
        added = db.stories.save(conn, source.id, entries, now, fresh_since)
        total += added
        name = result.title if source.name == db.sources.host(source.url) else None
        db.sources.record_success(
            conn, source.id, now, next_due(now, db.fetcher.get_interval(conn), 0), name
        )
        log.info("%s: %d new", source.url, added)
    return total


def run_forever(path: Path, stop: threading.Event, poll: float = 2.0) -> None:
    conn = db.connect(path)
    next_prune = datetime.min.replace(tzinfo=UTC)
    try:
        while not stop.is_set():
            try:
                now = datetime.now(UTC)
                db.fetcher.heartbeat(conn, now)
                state = db.fetcher.get(conn)
                if state.running:
                    fresh = int(db.settings.get(conn, "fresh_minutes"))
                    since = now - timedelta(minutes=fresh) if fresh else None
                    added = run_pass(conn, now, fresh_since=since)
                    if added is not None:
                        db.fetcher.record_pass(conn, datetime.now(UTC), added)
                if now >= next_prune:
                    trash_days = int(db.settings.get(conn, "trash_days"))
                    news_days = int(db.settings.get(conn, "news_days"))
                    db.cleanup.prune(conn, now, trash_days, news_days)
                    next_prune = now + PRUNE_EVERY
            except Exception:
                log.exception("Fetch loop failed; retrying")
                stop.wait(RETRY_DELAY)
                continue
            stop.wait(poll)
    finally:
        conn.close()
