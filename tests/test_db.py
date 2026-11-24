from datetime import UTC, datetime, timedelta

import pytest

from newscout import db
from newscout.models import Entry

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def stories(conn):
    rows = conn.execute(
        "SELECT title, sort_at, event_id FROM stories ORDER BY sort_at DESC, id DESC"
    )
    return [dict(row) for row in rows]


def kept(conn, source, *titles, when=NOW):
    db.stories.save(conn, source, [entry(t, when) for t in titles], when)
    for story in db.stories.waiting(conn, 100):
        db.stories.keep(conn, story.id, story.title, story.summary)


def entry(guid, published_at=None):
    return Entry(guid=guid, title=guid, link="", summary="", published_at=published_at)


def test_same_entry_is_stored_once(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    assert db.stories.save(conn, source, [entry("a")], NOW) == 1
    assert db.stories.save(conn, source, [entry("a")], NOW) == 0
    assert len(stories(conn)) == 1


def test_duplicate_source_raises(conn):
    db.sources.add(conn, "https://example.com/feed")
    with pytest.raises(db.sources.DuplicateSource):
        db.sources.add(conn, "https://example.com/feed")


def test_delete_source_removes_its_stories(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    db.stories.save(conn, source, [entry("a")], NOW)
    db.sources.delete(conn, source)
    assert stories(conn) == []
    assert db.news.list_page(conn) == []
    assert db.sources.list_all(conn) == []


def test_due_sources_respects_next_due_and_enabled(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    paused = db.sources.add(conn, "https://example.org/feed")
    db.sources.set_enabled(conn, paused, False)
    assert [s.id for s in db.sources.due(conn, NOW)] == [source]
    db.sources.record_success(conn, source, NOW, NOW + timedelta(minutes=15), None)
    assert db.sources.due(conn, NOW) == []
    assert [s.id for s in db.sources.due(conn, NOW + timedelta(minutes=15))] == [source]


def test_failure_then_success_resets_error(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    db.sources.record_failure(conn, source, NOW, NOW, "boom")
    failed = db.sources.get(conn, source)
    assert failed.failures == 1 and failed.last_error == "boom"
    db.sources.record_success(conn, source, NOW, NOW, None)
    ok = db.sources.get(conn, source)
    assert ok.failures == 0 and ok.last_error is None and ok.last_success_at == NOW


def test_missing_or_future_dates_sort_by_fetch_time(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    db.stories.save(
        conn,
        source,
        [
            entry("old", NOW - timedelta(hours=1)),
            entry("none"),
            entry("future", NOW + timedelta(days=1)),
        ],
        NOW,
    )
    rows = stories(conn)
    assert rows[-1]["title"] == "old"
    future = next(r for r in rows if r["title"] == "future")
    assert future["sort_at"] == NOW.isoformat()


def test_save_for_deleted_source_returns_zero(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    db.sources.delete(conn, source)
    assert db.stories.save(conn, source, [entry("a")], NOW) == 0


def test_new_database_starts_stopped(conn):
    state = db.fetcher.get(conn)
    assert state.running is False and state.heartbeat_at is None


def test_start_makes_backed_off_sources_due(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    db.sources.record_failure(conn, source, NOW, NOW + timedelta(hours=6), "down")
    assert db.sources.due(conn, NOW) == []
    db.fetcher.start(conn)
    assert [s.id for s in db.sources.due(conn, NOW)] == [source]


def test_stats_counts(conn):
    ok = db.sources.add(conn, "https://ok.example/feed")
    failing = db.sources.add(conn, "https://bad.example/feed")
    paused = db.sources.add(conn, "https://paused.example/feed")
    db.sources.record_failure(conn, failing, NOW, NOW, "down")
    db.sources.set_enabled(conn, paused, False)
    db.stories.save(conn, ok, [entry("old")], NOW - timedelta(days=1))
    db.stories.save(conn, ok, [entry("a"), entry("b")], NOW)
    stats = db.stats.summary(conn, since=NOW - timedelta(hours=1))
    assert (stats.today, stats.active_sources, stats.failing_sources) == (2, 2, 1)


def test_new_interval_applies_now_to_healthy_sources_only(conn):
    assert db.fetcher.get_interval(conn) == 15
    healthy = db.sources.add(conn, "https://ok.example/feed")
    failing = db.sources.add(conn, "https://bad.example/feed")
    db.sources.record_success(conn, healthy, NOW, NOW + timedelta(hours=1), None)
    db.sources.record_failure(conn, failing, NOW, NOW + timedelta(hours=2), "down")
    db.fetcher.set_interval(conn, 5)
    assert db.fetcher.get_interval(conn) == 5
    assert db.sources.get(conn, healthy).next_due_at is None
    assert db.sources.get(conn, failing).next_due_at == NOW + timedelta(hours=2)


def test_hourly_counts_and_last_hour(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    db.stories.save(conn, source, [entry("a"), entry("b")], NOW - timedelta(minutes=10))
    db.stories.save(conn, source, [entry("c")], NOW - timedelta(hours=3, minutes=10))
    hourly = db.stats.hourly(conn, NOW, hours=6)
    assert len(hourly) == 6
    assert hourly[-1] == 2 and hourly[-4] == 1 and sum(hourly) == 3
    assert db.stats.count_since(conn, NOW - timedelta(hours=1)) == 2


def test_settings_round_trip(conn):
    assert db.settings.get(conn, "deepseek_api_key") is None
    db.settings.put(conn, "deepseek_api_key", "sk-123")
    assert db.settings.get(conn, "deepseek_api_key") == "sk-123"
    db.settings.put(conn, "deepseek_api_key", "")
    assert db.settings.get(conn, "deepseek_api_key") is None


def test_new_stories_wait_for_ai_and_old_ones_are_skipped(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    fresh, stale = (
        entry("fresh", NOW - timedelta(minutes=10)),
        entry("stale", NOW - timedelta(hours=3)),
    )
    db.stories.save(conn, source, [fresh, stale, entry("dateless")], NOW, NOW - timedelta(hours=1))
    assert {s.title for s in db.stories.list_raw(conn)} == {"fresh", "dateless"}
    assert db.stories.counts(conn) == {"waiting": 2, "skipped": 1}
    assert db.stats.skipped_since(conn, NOW - timedelta(minutes=1)) == 1
    assert db.stories.save(conn, source, [stale], NOW) == 0


def test_keep_and_attach_build_news_events(conn):
    a = db.sources.add(conn, "https://a.example/feed")
    b = db.sources.add(conn, "https://b.example/feed")
    db.stories.save(conn, a, [entry("NTV", NOW - timedelta(hours=1))], NOW)
    db.stories.save(conn, b, [entry("Sözcü", NOW)], NOW)
    first, second = db.stories.waiting(conn, 10)
    event = db.stories.keep(conn, first.id, "Göçük", "Özet")
    db.stories.attach(conn, second.id, event, "Güngören'de göçük", "Yeni özet")
    (news,) = db.news.list_page(conn)
    assert news.title == "Güngören'de göçük" and news.summary == "Yeni özet"
    assert [s.source_name for s in news.sources] == ["a.example", "b.example"]
    assert news.sort_at == NOW and news.merged
    assert db.stories.counts(conn) == {"kept": 1, "merged": 1}


def test_trashing_a_raw_story_removes_it_from_news(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    kept(conn, source, "a")
    (story,) = db.stories.list_raw(conn)
    db.stories.set_status(conn, story.id, "trash", "by hand")
    assert db.news.list_page(conn) == []
    assert db.stories.get(conn, story.id).reason == "by hand"
    with pytest.raises(ValueError):
        db.stories.set_status(conn, story.id, "published")


def test_start_and_stop_round_trip(conn):
    db.fetcher.start(conn)
    assert db.fetcher.get(conn).running
    db.fetcher.stop(conn)
    assert db.fetcher.get(conn).running is False


def test_prune_forgets_news_after_the_keep_window(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    kept(conn, source, "ancient", when=NOW - timedelta(days=40))
    kept(conn, source, "fresh")
    db.cleanup.prune(conn, NOW, trash_days=7, news_days=30)
    assert [e.title for e in db.news.list_page(conn)] == ["fresh"]
    assert len(stories(conn)) == 1


def test_statuses_since_count_what_the_ai_did_with_todays_stories(conn):
    a = db.sources.add(conn, "https://a.example/feed")
    b = db.sources.add(conn, "https://b.example/feed")
    kept(conn, a, "1")
    db.stories.save(conn, b, [entry("2"), entry("3")], NOW)
    first, _ = db.stories.waiting(conn, 10)
    db.stories.attach(conn, first.id, db.news.list_page(conn)[0].id, "t", "s")
    since = NOW - timedelta(hours=1)
    assert db.stats.statuses_since(conn, since) == {"kept": 1, "merged": 1, "waiting": 1}
    assert db.stats.statuses_since(conn, NOW + timedelta(hours=1)) == {}


def test_latest_ids_and_counts(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    assert db.stats.latest_id(conn, "events") == 0
    kept(conn, source, "a", "b")
    first = db.stats.latest_id(conn, "stories")
    db.stories.save(conn, source, [entry("c")], NOW)
    assert db.stats.count_after(conn, "stories", first) == 1
    with pytest.raises(ValueError):
        db.stats.latest_id(conn, "sources; DROP TABLE x")


def test_skipped_stories_do_not_count_as_fetched_news(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    old = entry("old", NOW - timedelta(days=2))
    db.stories.save(conn, source, [old, entry("new")], NOW, NOW - timedelta(hours=1))
    since = NOW - timedelta(minutes=5)
    assert db.stats.summary(conn, since).today == 1
    assert db.stats.count_since(conn, since) == 1
    assert sum(db.stats.hourly(conn, NOW + timedelta(minutes=1), hours=2)) == 1


def test_trashing_news_sends_its_raw_stories_to_trash(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    kept(conn, source, *[str(n) for n in range(5)])
    ids = [e.id for page in range(3) for e in db.news.list_page(conn, limit=2, offset=page * 2)]
    assert len(ids) == 5 and len(set(ids)) == 5
    db.news.trash(conn, ids[0])
    assert db.news.count(conn) == 4
    assert db.stories.counts(conn) == {"kept": 4, "trash": 1}
    (trashed,) = db.stories.list_raw(conn, statuses=("trash",))
    assert trashed.reason == "Trashed by you" and trashed.event_id is None


def test_prune_empties_old_trash_but_remembers_the_story(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    kept(conn, source, "old", when=NOW - timedelta(days=10))
    db.news.trash(conn, db.news.list_page(conn)[0].id)
    db.cleanup.prune(conn, NOW, trash_days=7, news_days=30)
    assert db.stories.list_raw(conn) == []
    assert db.stories.save(conn, source, [entry("old")], NOW) == 0


def test_clear_news_keeps_sources_and_pauses(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    kept(conn, source, "a")
    db.fetcher.start(conn)
    db.cleanup.clear_all(conn)
    assert db.stories.list_raw(conn) == [] and db.news.count(conn) == 0
    assert [s.id for s in db.sources.list_all(conn)] == [source]
    assert db.fetcher.get(conn).running is False


def test_deleted_news_stays_gone(conn):
    source = db.sources.add(conn, "https://example.com/feed")
    kept(conn, source, "old", when=NOW - timedelta(days=3))
    kept(conn, source, "new")
    assert db.cleanup.delete_older_than(conn, NOW - timedelta(days=1)) == 1
    assert [e.title for e in db.news.list_page(conn)] == ["new"]
    assert db.stories.save(conn, source, [entry("old")], NOW) == 0
    assert db.cleanup.delete_status(conn, "kept") == 1
    assert db.news.count(conn) == 0
    with pytest.raises(ValueError):
        db.cleanup.delete_status(conn, "gone")


def test_times_in_other_zones_compare_correctly(conn):
    from datetime import timezone

    source = db.sources.add(conn, "https://example.com/feed")
    db.stories.save(conn, source, [entry("late")], NOW)
    istanbul_midnight = (NOW - timedelta(hours=1)).astimezone(timezone(timedelta(hours=3)))
    assert db.stats.count_since(conn, istanbul_midnight) == 1
