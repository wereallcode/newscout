from pathlib import Path

import httpx
import pytest

from newscout.fetch.collectors import FeedError
from newscout.fetch.collectors.rss import RssCollector, parse
from newscout.models import Source

FIXTURES = Path(__file__).parent / "fixtures"


def source():
    return Source(
        1, 1, "rss", "example.com", "https://example.com/feed", True, None, None, None, 0, None
    )


def collector(handler):
    return RssCollector(client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_parse_reads_items_and_feed_title():
    result = parse((FIXTURES / "feed.xml").read_bytes())
    assert result.title == "Fixture Feed"
    assert len(result.entries) == 3
    assert result.entries[0].published_at.year == 2026


def test_entry_without_link_or_date_uses_fallbacks():
    entry = parse((FIXTURES / "feed.xml").read_bytes()).entries[2]
    assert entry.guid == "No link story"
    assert entry.link == ""
    assert entry.published_at is None


def test_summary_is_plain_text():
    entries = parse((FIXTURES / "feed.xml").read_bytes()).entries
    assert entries[0].summary == "Tom & Jerry are back."
    assert entries[1].summary.endswith("…")
    assert len(entries[1].summary) <= 281


def test_garbage_raises_feed_error():
    garbage = (FIXTURES / "garbage.txt").read_bytes()
    with pytest.raises(FeedError):
        collector(lambda request: httpx.Response(200, content=garbage)).fetch(source())


def test_http_error_raises():
    with pytest.raises(httpx.HTTPStatusError):
        collector(lambda request: httpx.Response(500)).fetch(source())
