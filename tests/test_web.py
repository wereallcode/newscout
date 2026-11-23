from datetime import UTC, datetime, timedelta

import pytest

from newscout import db, presets
from newscout.ai.deepseek import KeyCheck
from newscout.models import Entry
from newscout.web import create_app

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def client(path):
    return create_app(path).test_client()


@pytest.fixture
def conn(path):
    connection = db.connect(path)
    yield connection
    connection.close()


def keep_all(conn):
    """Stands in for the AI: every waiting story becomes news of its own."""
    for waiting in db.stories.waiting(conn, 1000):
        db.stories.keep(conn, waiting.id, waiting.title, waiting.summary)


def story(conn, url, title, link="https://x.test", when=NOW):
    source = db.sources.add(conn, url)
    db.stories.save(conn, source, [Entry(title, title, link, "", when)], when)
    keep_all(conn)
    return source


def test_stories_render_without_fetcher(client, conn):
    story(conn, "https://a.example/feed", "Hello world")
    response = client.get("/")
    assert response.status_code == 200
    assert "Hello world" in response.text


def test_empty_state(client):
    assert "The AI turns raw news into news here." in client.get("/").text


def test_html_in_titles_is_escaped(client, conn):
    story(conn, "https://a.example/feed", "<script>alert(1)</script>")
    text = client.get("/").text
    assert "&lt;script&gt;" in text
    assert "<script>alert" not in text


def test_add_source(client, conn):
    response = client.post("/sources", data={"url": " https://example.com/feed "})
    assert response.status_code == 302
    assert [s.url for s in db.sources.list_all(conn)] == ["https://example.com/feed"]
    assert "Waiting" in client.get("/sources").text


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "Enter a valid URL."),
        ("example.com", "Enter a valid URL."),
        ("javascript:alert(1)", "Enter a valid URL."),
        ("ftp://example.com/feed", "Enter a valid URL."),
        ("https://dup.example/feed", "Already added."),
    ],
)
def test_rejects_bad_urls(client, conn, url, message):
    db.sources.add(conn, "https://dup.example/feed")
    response = client.post("/sources", data={"url": url}, follow_redirects=True)
    assert message in response.text
    assert len(db.sources.list_all(conn)) == 1


def test_toggle_and_delete(client, conn):
    source = db.sources.add(conn, "https://example.com/feed")
    client.post(f"/sources/{source}/toggle")
    assert db.sources.get(conn, source).enabled is False
    client.post(f"/sources/{source}/delete")
    assert db.sources.get(conn, source) is None
    assert client.post("/sources/999/delete").status_code == 404


def test_pages_with_previous_and_next(client, conn, monkeypatch):
    monkeypatch.setattr("newscout.web.views.dashboard.PAGE_SIZE", 2)
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(
        conn, source, [Entry(f"s{n}", f"Story {n}", "", "", None) for n in range(5)], NOW
    )
    keep_all(conn)
    first = client.get("/").text
    assert first.count('class="story"') == 2
    assert "Page 1 of 3" in first and 'href="/?page=2#news"' in first
    assert 'aria-disabled="true">' in first.split("Page 1 of 3")[0][-300:]
    last = client.get("/?page=3").text
    assert last.count('class="story"') == 1
    assert "Page 3 of 3" in last and 'href="/?page=2#news"' in last


def test_bad_or_out_of_range_page_is_clamped(client, conn):
    story(conn, "https://a.example/feed", "Hello")
    for page in ("nonsense", "0", "99"):
        assert "Hello" in client.get(f"/?page={page}").text


def test_single_page_has_no_pager(client, conn):
    story(conn, "https://a.example/feed", "Hello")
    assert "Page 1 of" not in client.get("/").text


def test_story_without_link_is_plain_text(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(conn, source, [Entry("x", "No link", "", "", NOW)], NOW)
    keep_all(conn)
    text = client.get("/").text
    assert '<span class="title">No link</span>' in text


def test_queue_is_not_auto_replaced(client):
    text = client.get("/").text
    assert 'id="news"' in text
    assert 'id="news" data-live' not in text


def test_nav_has_no_news_tab(client):
    assert ">News</span>" not in client.get("/").text


def test_control_room_shows_fetcher_choices_and_start(client, conn):
    db.fetcher.set_interval(conn, 30)
    text = client.get("/control").text
    assert 'class="chip-option on" type="submit" name="interval" value="30"' in text
    assert 'action="/fetcher/start"' in text


def test_top_bar_starts_and_pauses_the_fetcher_from_any_page(client, conn):
    db.fetcher.heartbeat(conn, datetime.now(UTC))
    assert 'action="/fetcher/start"' in client.get("/sources").text
    response = client.post("/fetcher/start", headers={"Referer": "http://localhost/sources"})
    assert response.headers["Location"].endswith("/sources")
    assert db.fetcher.get(conn).running is True
    assert 'action="/fetcher/stop"' in client.get("/sources").text
    client.post("/fetcher/stop")
    assert db.fetcher.get(conn).running is False


def test_settings_saves_the_new_window(client, conn):
    response = client.post("/settings", data={"new_minutes": "5"}, follow_redirects=True)
    assert db.settings.get(conn, "new_minutes") == "5"
    assert "Saved" in response.text
    assert 'value="5"' in client.get("/settings").text


@pytest.mark.parametrize("value", ["0", "1441", "abc", ""])
def test_settings_rejects_bad_new_window(client, conn, value):
    response = client.post("/settings", data={"new_minutes": value}, follow_redirects=True)
    assert "Enter a number in range." in response.text
    assert db.settings.get(conn, "new_minutes") == "30"


def test_dashboard_has_no_search_or_step_heading(client, conn):
    story(conn, "https://a.example/feed", "Hello")
    text = client.get("/").text
    assert 'type="search"' not in text
    assert "In Collect" not in text


def test_stop(client, conn):
    db.fetcher.start(conn)
    client.post("/fetcher/stop")
    assert db.fetcher.get(conn).running is False


def test_fetcher_on_fresh_db_says_not_responding(client):
    response = client.get("/control")
    assert response.status_code == 200
    assert "Not working" in response.text


def test_fetcher_running_with_fresh_heartbeat(client, conn):
    db.fetcher.start(conn)
    db.fetcher.heartbeat(conn, datetime.now(UTC))
    assert "Running" in client.get("/control").text
    assert 'class="switch running"' in client.get("/").text


def test_cockpit_page_is_gone(client):
    assert client.get("/cockpit").status_code == 404


def test_next_pass_wording():
    from newscout.web.display import ago_or_in

    now = datetime.now(UTC)
    assert ago_or_in(None) == "now"
    assert ago_or_in(now - timedelta(minutes=3)) == "now"
    assert ago_or_in(now + timedelta(seconds=30)) == "now"
    assert ago_or_in(now + timedelta(minutes=14, seconds=30)) == "in 14m"


def stories_in_newsroom(conn, *titles):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(conn, source, [Entry(t, t, "", "", NOW) for t in titles], NOW)
    keep_all(conn)
    return {e.title: e.id for e in db.news.list_page(conn)}


def test_stats_live_on_the_fetcher_page(client, conn):
    now = datetime.now(UTC)
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(
        conn, source, [Entry(f"s{n}", f"Story {n}", "", "", now) for n in range(7)], now
    )
    keep_all(conn)
    dashboard = client.get("/").text
    assert dashboard.count('class="story"') == 7
    assert 'data-count="newsroom">7<' in dashboard
    assert "data-stat" not in dashboard
    assert "<span>Last hour</span><b>7</b>" in client.get("/control").text


def test_numbers_stay_with_their_event(client, conn):
    keep = db.sources.add(conn, "https://keep.example/feed")
    gone = db.sources.add(conn, "https://gone.example/feed")
    db.stories.save(conn, keep, [Entry("k", "Keep", "", "", NOW - timedelta(hours=1))], NOW)
    keep_all(conn)
    db.stories.save(conn, gone, [Entry("g", "Gone", "", "", NOW)], NOW)
    keep_all(conn)
    number = next(e.id for e in db.news.list_page(conn) if e.title == "Keep")
    assert f'<span class="rank">#{number}</span>' in client.get("/").text
    db.sources.delete(conn, gone)
    assert f'<span class="rank">#{number}</span>' in client.get("/").text


def test_recent_news_is_marked_new(client, conn):
    now = datetime.now(UTC)
    source = db.sources.add(conn, "https://a.example/feed")
    fresh = Entry("f", "Fresh", "", "", now - timedelta(minutes=10))
    old = Entry("o", "Old", "", "", now - timedelta(minutes=50))
    db.stories.save(conn, source, [fresh, old], now)
    keep_all(conn)
    text = client.get("/").text
    assert text.count('class="new-tag"') == 1
    db.settings.put(conn, "new_minutes", "60")
    assert client.get("/").text.count('class="new-tag"') == 2


def test_fetcher_interval_rejects_out_of_range(client, conn):
    for value in ("0", "1441"):
        client.post("/fetcher/interval", data={"interval": value})
    assert db.fetcher.get_interval(conn) == 15


def test_unknown_step_falls_back_to_newsroom(client, conn):
    stories_in_newsroom(conn, "Hello")
    assert "Hello" in client.get("/?step=nope").text


def test_news_has_trash_but_no_send_button(client, conn):
    stories_in_newsroom(conn, "Hello")
    text = client.get("/").text
    assert "Move to trash" in text
    assert "Send to" not in text


def test_single_event_has_no_merged_badge(client, conn):
    story(conn, "https://a.example/feed", "Alone")
    assert "Merged" not in client.get("/").text


@pytest.fixture(autouse=True)
def key_check(monkeypatch):
    """Keys are checked against DeepSeek when saved; tests answer instead of the network."""
    results = {"sk-bad": KeyCheck(False, "DeepSeek rejected this key.")}
    monkeypatch.setattr(
        "newscout.web.views.control.check_key",
        lambda key: results.get(key, KeyCheck(True, "Key works with a balance of 4.20 USD.")),
    )


def test_api_key_is_saved_masked_and_removable(client, conn):
    response = client.post("/ai/key", data={"api_key": " sk-abcdef1234 "}, follow_redirects=True)
    assert "Key works with a balance of 4.20 USD" in response.text
    assert db.settings.get(conn, "deepseek_api_key") == "sk-abcdef1234"
    page = client.get("/control").text
    assert "sk-abcdef1234" not in page and "DeepSeek key saved" in page
    assert "Ends with 1234 · Working" in page
    client.post("/ai/key", data={"remove": "1"})
    assert db.settings.get(conn, "deepseek_api_key") is None


def test_empty_api_key_keeps_the_saved_one(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-keep")
    client.post("/ai/key", data={"api_key": ""})
    assert db.settings.get(conn, "deepseek_api_key") == "sk-keep"


def test_failing_sources_are_not_counted_as_working(client, conn):
    ok = db.sources.add(conn, "https://ok.example/feed")
    bad = db.sources.add(conn, "https://bad.example/feed")
    db.sources.record_success(conn, ok, NOW, NOW, None)
    db.sources.record_failure(conn, bad, NOW, NOW, "down")
    assert "1<small>/2</small>" in client.get("/control").text


def test_retry_makes_a_failing_source_due_again(client, conn):
    source = db.sources.add(conn, "https://bad.example/feed")
    db.sources.record_failure(conn, source, NOW, NOW + timedelta(hours=6), "down")
    assert "Retry" in client.get("/sources").text
    client.post(f"/sources/{source}/retry")
    assert [s.id for s in db.sources.due(conn, NOW)] == [source]
    assert client.post("/sources/999/retry").status_code == 404


def test_control_room_numbers_come_before_the_fetcher_and_ai(client):
    text = client.get("/control").text
    assert text.index('id="numbers"') < text.index('id="units"')


def test_fetcher_interval_presets(client, conn):
    assert 'name="interval" value="30"' in client.get("/control").text
    client.post("/fetcher/interval", data={"interval": "30"})
    assert db.fetcher.get_interval(conn) == 30
    client.post("/fetcher/interval", data={"interval": "abc"})
    assert db.fetcher.get_interval(conn) == 30


def test_check_now_makes_every_source_due(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.sources.record_success(conn, source, NOW, NOW + timedelta(hours=1), None)
    client.post("/fetcher/check")
    assert [s.id for s in db.sources.due(conn, NOW)] == [source]


def test_interval_lives_only_on_the_fetcher_page(client):
    assert 'name="interval"' not in client.get("/settings").text


def test_ai_problem_is_shown_in_the_control_room(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-abcd")
    db.settings.put(conn, "ai_running", "1")
    db.settings.put(conn, "ai_status", "Problem: 401 Unauthorized")
    assert "401 Unauthorized" in client.get("/control").text


def test_delete_source_asks_first(client, conn):
    db.sources.add(conn, "https://a.example/feed")
    assert "confirm(" in client.get("/sources").text


def test_posts_from_other_sites_are_refused(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    response = client.post(f"/sources/{source}/delete", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert db.sources.get(conn, source) is not None
    same = client.post(f"/sources/{source}/delete", headers={"Origin": "http://localhost"})
    assert same.status_code == 302


def test_first_run_guide_when_there_are_no_sources(client, conn):
    text = client.get("/").text
    assert "Add a news source" in text and "Start the fetcher" in text
    db.sources.add(conn, "https://a.example/feed")
    assert "Add a news source" not in client.get("/").text


def test_merged_today_on_the_fetcher_page(client):
    assert "Merged today" in client.get("/control").text


def test_keep_settings(client, conn):
    client.post("/settings", data={"new_minutes": "30", "trash_days": "3", "news_days": "14"})
    assert db.settings.get(conn, "trash_days") == "3"
    assert db.settings.get(conn, "news_days") == "14"
    client.post("/settings", data={"new_minutes": "30", "trash_days": "0", "news_days": "14"})
    assert db.settings.get(conn, "trash_days") == "3"


def test_start_and_stop(client, conn):
    client.post("/fetcher/start")
    assert db.fetcher.get(conn).running
    client.post("/fetcher/stop")
    assert db.fetcher.get(conn).running is False


def test_raw_shows_every_story_with_what_the_ai_did(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    entries = [Entry(t, t, "", "", NOW) for t in ("Waits", "Kept", "Joined", "Sport")]
    db.stories.save(conn, source, entries, NOW)
    waiting = {s.title: s.id for s in db.stories.waiting(conn, 10)}
    event = db.stories.keep(conn, waiting["Kept"], "Kept", "")
    db.stories.attach(conn, waiting["Joined"], event, "Kept", "")
    db.stories.set_status(conn, waiting["Sport"], "dropped", "sports")
    text = client.get("/?step=raw").text
    assert 'title="Waiting for the AI"' in text
    assert f'title="News #{event}"' in text and f'title="Merged into news #{event}"' in text
    assert 'title="Dropped by the AI: sports"' in text
    dropped = client.get("/?step=raw&show=dropped").text
    assert "Sport" in dropped and "Waits" not in dropped


def test_news_only_shows_what_the_ai_kept(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(conn, source, [Entry("x", "Unchecked", "", "", NOW)], NOW)
    assert "Unchecked" not in client.get("/").text
    assert "Unchecked" in client.get("/?step=raw&show=waiting").text


def test_ai_instructions_live_on_the_raw_tab(client, conn):
    assert "AI Instructions" in client.get("/?step=raw").text
    assert "AI Instructions" not in client.get("/").text
    assert "Merge stories that report the same real-world event" in client.get("/?step=raw").text


def test_ai_instructions_can_be_edited_and_reset(client, conn):
    form = {"merge": "Same event.", "rewrite": "Be brief."}
    client.post("/instructions", data=form)
    assert db.settings.get(conn, "ai_merge") == "Same event."
    assert "Be brief." in client.get("/?step=raw").text
    client.post("/instructions", data={**form, "reset": "1"})
    assert db.settings.get(conn, "ai_merge") is None


def test_merged_news_shows_its_sources(client, conn):
    a = db.sources.add(conn, "https://ntv.example/feed")
    b = db.sources.add(conn, "https://sozcu.example/feed")
    db.stories.save(conn, a, [Entry("1", "NTV göçük", "https://ntv.example/1", "", NOW)], NOW)
    db.stories.save(conn, b, [Entry("2", "Sözcü göçük", "https://sozcu.example/2", "", NOW)], NOW)
    first, second = db.stories.waiting(conn, 10)
    event = db.stories.keep(conn, first.id, "x", "")
    db.stories.attach(conn, second.id, event, "Güngören'de göçük", "Özet.")
    text = client.get("/").text
    assert text.count('class="story merged"') == 1
    assert "Güngören&#39;de göçük" in text and 'title="Merged from 2 sources"' in text
    assert 'href="https://ntv.example/1"' in text and 'href="https://sozcu.example/2"' in text


def test_latest_counts_per_tab(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    news = client.get("/api/latest?tab=news").json["latest"]
    raw = client.get("/api/latest?tab=raw").json["latest"]
    db.stories.save(
        conn, source, [Entry("1", "One", "", "", NOW), Entry("2", "Two", "", "", NOW)], NOW
    )
    assert client.get(f"/api/latest?tab=raw&since={raw}").json["new"] == 2
    assert client.get(f"/api/latest?tab=news&since={news}").json["new"] == 0
    keep_all(conn)
    assert client.get(f"/api/latest?tab=news&since={news}").json["new"] == 2


def test_raw_count_is_only_what_waits_and_done_rows_are_faded(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(
        conn, source, [Entry("1", "Done", "", "", NOW), Entry("2", "Wait", "", "", NOW)], NOW
    )
    done = next(s for s in db.stories.waiting(conn, 10) if s.title == "Done")
    db.stories.keep(conn, done.id, "Done", "")
    text = client.get("/?step=raw").text
    assert 'data-count="raw">1<' in text
    assert 'class="story raw kept"' in text


def test_newsroom_name(client):
    assert "Newsroom" in client.get("/").text


def test_skipped_count_on_the_fetcher_page(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    old = Entry("o", "Old", "", "", datetime.now(UTC) - timedelta(days=2))
    db.stories.save(conn, source, [old], datetime.now(UTC), datetime.now(UTC) - timedelta(hours=1))
    assert "<span>Skipped as old</span><b>1</b>" in client.get("/control").text


def test_two_tabs_without_roadmap_cards(client):
    text = client.get("/").text
    assert 'href="/?step=raw"' in text and "Newsroom" in text
    assert "step=trash" not in text
    assert "soon" not in text.lower()


def test_trashing_news_moves_its_sources_to_raw_trash(client, conn):
    ids = stories_in_newsroom(conn, "Bin me")
    client.post(f"/events/{ids['Bin me']}/trash")
    assert db.news.get(conn, ids["Bin me"]) is None
    trash = client.get("/?step=raw&show=trash").text
    assert "Bin me" in trash and "Trash: Trashed by you" in trash
    assert client.post("/events/999/trash").status_code == 404


def test_raw_story_can_be_trashed_and_restored(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(conn, source, [Entry("x", "Bin me", "", "", NOW)], NOW)
    (story_,) = db.stories.waiting(conn, 10)
    client.post(f"/stories/{story_.id}/trash")
    assert db.stories.get(conn, story_.id).status == "trash"
    client.post(f"/stories/{story_.id}/restore")
    assert db.stories.get(conn, story_.id).status == "waiting"
    assert client.post("/stories/999/trash").status_code == 404


def test_raw_filters_with_counts(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(conn, source, [Entry(t, t, "", "", NOW) for t in ("A", "B")], NOW)
    first = db.stories.waiting(conn, 10)[0]
    db.stories.set_status(conn, first.id, "dropped", "sports")
    text = client.get("/?step=raw").text
    assert 'href="/?step=raw&amp;show=dropped"' in text
    assert "Dropped<span>1</span>" in text and "All<span>2</span>" in text
    assert "Waiting<span>1</span>" in text


def test_fetcher_freshness_choice(client, conn):
    assert 'name="fresh_minutes" value="0"' in client.get("/control").text
    client.post("/fetcher/freshness", data={"fresh_minutes": "0"})
    assert db.settings.get(conn, "fresh_minutes") == "0"
    assert (
        'class="chip-option on" type="submit" name="fresh_minutes" value="0"'
        in client.get("/control").text
    )
    client.post("/fetcher/freshness", data={"fresh_minutes": "7"})
    assert db.settings.get(conn, "fresh_minutes") == "0"


def test_delete_all_news_from_the_control_room(client, conn):
    story(conn, "https://a.example/feed", "Gone soon")
    assert "Delete all news" not in client.get("/settings").text
    assert "Delete all news" in client.get("/control").text
    client.post("/clean-up/all")
    assert db.news.count(conn) == 0 and db.stories.list_raw(conn) == []
    assert len(db.sources.list_all(conn)) == 1


def test_delete_news_older_than_a_few_days(client, conn):
    story(conn, "https://a.example/feed", "Old", when=datetime.now(UTC) - timedelta(days=10))
    story(conn, "https://b.example/feed", "Fresh", when=datetime.now(UTC))
    response = client.post("/clean-up/older", data={"days": "7"}, follow_redirects=True)
    assert "Deleted 1 raw story." in response.text
    assert [e.title for e in db.news.list_page(conn)] == ["Fresh"]
    client.post("/clean-up/older", data={"days": "2"})
    assert db.news.count(conn) == 1


def test_delete_news_by_label(client, conn):
    story(conn, "https://a.example/feed", "Kept")
    source = db.sources.add(conn, "https://b.example/feed")
    db.stories.save(conn, source, [Entry("w", "Waiting", "", "", NOW)], NOW)
    assert 'name="status" value="waiting"' in client.get("/control").text
    client.post("/clean-up/label", data={"status": "waiting"})
    assert db.stories.counts(conn) == {"kept": 1, "gone": 1}
    client.post("/clean-up/label", data={"status": "gone"})
    assert db.stories.counts(conn) == {"kept": 1, "gone": 1}


def test_top_bar_shows_fetcher_state(client, conn):
    db.sources.add(conn, "https://a.example/feed")
    for page in ("/", "/sources", "/settings"):
        assert 'class="switch not-responding"' in client.get(page).text
    db.fetcher.heartbeat(conn, datetime.now(UTC))
    assert 'class="switch stopped"' in client.get("/").text
    db.fetcher.start(conn)
    assert 'class="switch running"' in client.get("/").text


def test_top_bar_ai_state(client, conn):
    assert 'class="switch off"' in client.get("/").text
    db.settings.put(conn, "deepseek_api_key", "sk-x")
    assert 'class="switch paused"' in client.get("/").text
    db.settings.put(conn, "ai_running", "1")
    assert 'class="switch on"' in client.get("/").text
    db.settings.put(conn, "ai_status", "Problem: 401")
    assert 'class="switch problem"' in client.get("/").text
    assert "AI is off" not in client.get("/").text


def test_control_room_says_when_ai_needs_a_key(client, conn):
    assert "Add a DeepSeek key to start." in client.get("/control").text
    db.settings.put(conn, "deepseek_api_key", "sk-x")
    assert "Add a DeepSeek key to start." not in client.get("/control").text


def test_a_new_key_clears_the_old_problem(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-old")
    db.settings.put(conn, "ai_status", "Problem: 401")
    client.post("/ai/key", data={"api_key": "sk-new"})
    assert db.settings.get(conn, "ai_status") == "ok"
    assert 'class="switch on"' in client.get("/").text


def test_rejected_key_is_not_saved(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-keep")
    response = client.post("/ai/key", data={"api_key": "sk-bad"}, follow_redirects=True)
    assert "DeepSeek rejected this key." in response.text
    assert db.settings.get(conn, "deepseek_api_key") == "sk-keep"


def test_key_without_sk_prefix_is_explained(client, conn):
    response = client.post("/ai/key", data={"api_key": "f37abc"}, follow_redirects=True)
    assert "starts with sk-" in response.text
    assert db.settings.get(conn, "deepseek_api_key") is None


def test_test_button_checks_the_saved_key(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-bad")
    response = client.post("/ai/key/test", follow_redirects=True)
    assert "DeepSeek rejected this key." in response.text
    assert db.settings.get(conn, "ai_status") == "Problem: DeepSeek rejected this key."


def test_ai_starts_and_pauses_on_its_own(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-x")
    assert "/ai/start" in client.get("/").text
    client.post("/ai/start")
    assert db.settings.get(conn, "ai_running") == "1"
    assert db.fetcher.get(conn).running is False
    assert "/ai/stop" in client.get("/").text
    client.post("/ai/stop")
    assert not db.settings.get(conn, "ai_running")


def test_no_ai_toggle_without_a_key(client):
    assert "/ai/start" not in client.get("/").text


def test_newsroom_links_every_source_instead_of_the_original_titles(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    entry = Entry("g", "Original headline", "https://a.example/story", "", NOW)
    db.stories.save(conn, source, [entry], NOW)
    (waiting,) = db.stories.waiting(conn, 10)
    db.stories.keep(conn, waiting.id, "AI headline", "AI summary")
    text = client.get("/").text
    assert '<span class="title">AI headline</span>' in text
    assert 'href="https://a.example/story"' in text
    assert 'title="Original: Original headline"' in text
    assert ">Original headline<" not in text


def test_raw_shows_when_the_ai_found_a_story_relevant(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    db.stories.save(conn, source, [Entry("g", "Story", "", "", NOW)], NOW)
    assert "Relevant, waiting for the AI" not in client.get("/?step=raw").text
    db.stories.mark_relevant(conn, db.stories.waiting(conn, 1)[0].id)
    assert "Relevant, waiting for the AI" in client.get("/?step=raw").text


def test_control_room_is_highlighted_in_the_top_bar(client):
    nav = '<a href="/control" class="active">'
    assert nav in client.get("/control").text and nav not in client.get("/settings").text


def test_newsroom_language_is_chosen_in_the_control_room(client, conn):
    db.settings.put(conn, "deepseek_api_key", "sk-x")
    assert 'name="language" value="Turkish"' in client.get("/control").text
    assert 'name="language"' not in client.get("/?step=raw").text
    client.post("/ai/language", data={"language": "Turkish"})
    assert db.settings.get(conn, "news_language") == "Turkish"
    client.post("/ai/language", data={"language": "Klingon"})
    assert db.settings.get(conn, "news_language") is None


def test_groups_can_be_created_renamed_and_given_a_relevance(client, conn):
    client.post("/groups", data={"name": "  Tech   news "})
    (group,) = db.groups.list_all(conn)
    assert group.name == "Tech news"
    client.post("/sources", data={"url": "https://a.example/feed", "group_id": group.id})
    assert [s.group_id for s in db.sources.list_all(conn)] == [group.id]
    client.post(f"/groups/{group.id}", data={"name": "Tech", "relevance": "Only AI news."})
    assert db.groups.get(conn, group.id).relevance == "Only AI news."
    response = client.post("/groups", data={"name": "Tech"}, follow_redirects=True)
    assert "A group with this name already exists." in response.text


def test_paused_group_is_not_fetched(client, conn):
    source = db.sources.add(conn, "https://a.example/feed")
    group = db.sources.get(conn, source).group_id
    assert [s.id for s in db.sources.due(conn, NOW)] == [source]
    assert f'action="/groups/{group}/toggle"' in client.get("/control").text
    client.post(f"/groups/{group}/toggle")
    assert db.sources.due(conn, NOW) == []


@pytest.mark.parametrize(
    ("page", "title"),
    [
        ("/", "Dashboard"),
        ("/?step=raw", "Dashboard"),
        ("/control", "Control Room"),
        ("/sources", "Sources"),
        ("/settings", "Settings"),
    ],
)
def test_every_page_names_itself_in_the_tab(client, page, title):
    assert f"<title>{title} - Newscout</title>" in client.get(page).text


def test_settings_restores_a_deleted_preset(client, conn):
    presets.install(conn)
    gaming = next(g for g in db.groups.list_all(conn) if g.name == "Gaming News")
    assert "Restore" not in client.get("/settings").text
    db.groups.delete(conn, gaming.id)
    assert "Restore" not in client.get("/sources").text
    assert "Restore" in client.get("/settings").text
    response = client.post(
        "/settings/presets/restore", data={"name": "Gaming News"}, follow_redirects=True
    )
    assert "Gaming News restored. Switch it on in Control Room" in response.text
    assert "Gaming News" in {g.name for g in db.groups.list_all(conn)}
    assert "Restore" not in response.text
