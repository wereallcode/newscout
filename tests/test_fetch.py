import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from newscout import db
from newscout.fetch import loop
from newscout.models import Entry, FeedResult

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
REAL_RUN_PASS = loop.run_pass


@pytest.fixture
def path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(path):
    connection = db.connect(path)
    yield connection
    connection.close()


def titles(conn):
    return [row[0] for row in conn.execute("SELECT title FROM stories ORDER BY id")]


def entries(*guids):
    return [Entry(guid=g, title=g, link="", summary="", published_at=None) for g in guids]


class Fake:
    def __init__(self, routes):
        self.routes = routes

    def fetch(self, source):
        return self.routes[source.url]()


def run(conn, routes, **kwargs):
    loop.run_pass(conn, NOW, collectors={"rss": Fake(routes)}, steps=[], **kwargs)


def boom():
    raise RuntimeError("feed is down")


def test_one_bad_source_does_not_stop_others(conn):
    bad = db.sources.add(conn, "https://bad.example/feed")
    good = db.sources.add(conn, "https://good.example/feed")
    run(
        conn,
        {
            "https://bad.example/feed": boom,
            "https://good.example/feed": lambda: FeedResult("Good", entries("a", "b")),
        },
    )
    assert len(titles(conn)) == 2
    assert db.sources.get(conn, bad).failures == 1
    assert db.sources.get(conn, bad).last_error == "feed is down"
    assert db.sources.get(conn, good).last_error is None


def test_slow_source_times_out_alone(conn):
    slow = db.sources.add(conn, "https://slow.example/feed")
    db.sources.add(conn, "https://fast.example/feed")

    def sleepy():
        time.sleep(1)
        return FeedResult(None, entries("late"))

    run(
        conn,
        {
            "https://slow.example/feed": sleepy,
            "https://fast.example/feed": lambda: FeedResult(None, entries("a")),
        },
        timeout=0.2,
    )
    assert titles(conn) == ["a"]
    assert "Timed out" in db.sources.get(conn, slow).last_error


def test_backoff_doubles_and_caps():
    assert loop.next_due(NOW, 15, 0) == NOW + timedelta(minutes=15)
    assert loop.next_due(NOW, 15, 2) == NOW + timedelta(minutes=60)
    assert loop.next_due(NOW, 15, 10) == NOW + timedelta(hours=6)


def test_failure_schedules_backoff(conn):
    source = db.sources.add(conn, "https://bad.example/feed")
    run(conn, {"https://bad.example/feed": boom})
    assert db.sources.get(conn, source).next_due_at == NOW + timedelta(minutes=30)


def test_feed_title_fills_default_name(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    titles = iter(["Example", "Other"])
    routes = {"https://example.com/feed": lambda: FeedResult(next(titles), [])}
    run(conn, routes)
    assert db.sources.get(conn, source).name == "Example"
    loop.run_pass(conn, NOW + timedelta(hours=1), collectors={"rss": Fake(routes)}, steps=[])
    assert db.sources.get(conn, source).name == "Example"


def test_source_deleted_mid_fetch_is_skipped(conn, path):
    gone = db.sources.add(conn, "https://gone.example/feed")
    db.sources.add(conn, "https://kept.example/feed")

    def delete_then_return():
        other = db.connect(path)
        db.sources.delete(other, gone)
        other.close()
        return FeedResult("Gone", entries("x"))

    run(
        conn,
        {
            "https://gone.example/feed": delete_then_return,
            "https://kept.example/feed": lambda: FeedResult(None, entries("a")),
        },
    )
    assert titles(conn) == ["a"]
    assert db.sources.get(conn, gone) is None


def test_run_forever_survives_a_crashing_pass(path, monkeypatch):
    stop = threading.Event()
    calls = []

    def flaky(conn, now, **kwargs):
        calls.append(now)
        if len(calls) == 1:
            raise RuntimeError("database hiccup")
        stop.set()

    conn = db.connect(path)
    db.fetcher.start(conn)
    conn.close()
    monkeypatch.setattr(loop, "run_pass", flaky)
    monkeypatch.setattr(loop, "RETRY_DELAY", 0)
    loop.run_forever(path, stop, poll=0)
    assert len(calls) == 2


def test_fresh_since_sends_old_entries_to_trash(conn):
    db.sources.add(conn, "https://example.com/feed")
    items = [
        Entry("old", "old", "", "", NOW - timedelta(minutes=10)),
        Entry("new", "new", "", "", NOW - timedelta(minutes=2)),
        Entry("dateless", "dateless", "", "", None),
    ]
    run(
        conn,
        {"https://example.com/feed": lambda: FeedResult(None, items)},
        fresh_since=NOW - timedelta(minutes=5),
    )
    assert {s.title: s.status for s in db.stories.list_raw(conn)} == {
        "new": "waiting",
        "dateless": "waiting",
    }


def test_loop_uses_the_freshness_setting(conn, path, monkeypatch):
    db.sources.add(conn, "https://example.com/feed")
    db.fetcher.start(conn)
    db.settings.put(conn, "fresh_minutes", "30")
    now = datetime.now(UTC)
    items = [
        Entry("hour", "hour", "", "", now - timedelta(minutes=45)),
        Entry("recent", "recent", "", "", now - timedelta(minutes=5)),
    ]
    loop_once(path, monkeypatch, {"https://example.com/feed": lambda: FeedResult(None, items)})
    assert {s.title: s.status for s in db.stories.list_raw(conn)} == {"recent": "waiting"}


def test_run_pass_returns_none_when_nothing_due(conn):
    assert loop.run_pass(conn, NOW, collectors={}, steps=[]) is None


def loop_once(path, monkeypatch, routes, on_pass=None):
    stop = threading.Event()
    polls = []
    real = REAL_RUN_PASS

    def counting(conn, now, **kwargs):
        polls.append(now)
        result = real(conn, now, collectors={"rss": Fake(routes)}, steps=[], **kwargs)
        if on_pass:
            on_pass()
        return result

    original_wait = stop.wait

    def wait(timeout=None):
        if len(waits) >= 1:
            stop.set()
        waits.append(timeout)
        return original_wait(0)

    waits = []
    stop.wait = wait
    monkeypatch.setattr(loop, "run_pass", counting)
    loop.run_forever(path, stop, poll=0)
    return polls


def test_stopped_fetcher_only_heartbeats(conn, path, monkeypatch):
    db.sources.add(conn, "https://example.com/feed")
    polls = loop_once(path, monkeypatch, {})
    assert polls == []
    assert db.fetcher.get(conn).heartbeat_at is not None
    assert titles(conn) == []


def test_running_fetcher_passes_and_records(conn, path, monkeypatch):
    db.sources.add(conn, "https://example.com/feed")
    db.fetcher.start(conn)
    loop_once(
        path, monkeypatch, {"https://example.com/feed": lambda: FeedResult(None, entries("a", "b"))}
    )
    state = db.fetcher.get(conn)
    assert state.last_pass_added == 2 and state.last_pass_at is not None


def test_stop_between_polls_prevents_next_pass(conn, path, monkeypatch):
    db.sources.add(conn, "https://example.com/feed")
    db.fetcher.start(conn)

    def stop_now():
        other = db.connect(path)
        db.fetcher.stop(other)
        other.close()

    polls = loop_once(
        path,
        monkeypatch,
        {"https://example.com/feed": lambda: FeedResult(None, entries("a"))},
        on_pass=stop_now,
    )
    assert len(polls) == 1


def test_loop_prunes_old_news(conn, path, monkeypatch):
    source = db.sources.add(conn, "https://example.com/feed")
    db.stories.save(conn, source, entries("ancient"), datetime.now(UTC) - timedelta(days=40))
    loop_once(path, monkeypatch, {})
    assert titles(conn) == []


def test_any_time_freshness_keeps_old_news(conn, path, monkeypatch):
    db.sources.add(conn, "https://example.com/feed")
    db.fetcher.start(conn)
    db.settings.put(conn, "fresh_minutes", "0")
    old = Entry("old", "old", "", "", datetime.now(UTC) - timedelta(days=3))
    loop_once(path, monkeypatch, {"https://example.com/feed": lambda: FeedResult(None, [old])})
    assert [s.status for s in db.stories.list_raw(conn)] == ["waiting"]
