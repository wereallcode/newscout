import calendar
import html
import re
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser

import feedparser
import httpx

from newscout.fetch.collectors.base import FeedError
from newscout.models import Entry, FeedResult, Source

SUMMARY_LENGTH = 280


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    parser.close()
    text = re.sub(r"\s+", " ", html.unescape("".join(parser.parts))).strip()
    if len(text) > SUMMARY_LENGTH:
        text = text[:SUMMARY_LENGTH].rstrip() + "…"
    return text


def _date(item) -> datetime | None:
    parsed = item.get("published_parsed") or item.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), UTC) if parsed else None


def parse(content: bytes) -> FeedResult:
    feed = feedparser.parse(content)
    entries = []
    for item in feed.entries:
        title = plain(item.get("title", ""))
        link = item.get("link", "")
        guid = item.get("id") or link or title
        if not guid:
            continue
        entries.append(
            Entry(
                guid=guid,
                title=title or link,
                link=link,
                summary=plain(item.get("summary", "")),
                published_at=_date(item),
            )
        )
    return FeedResult(title=feed.feed.get("title") or None, entries=entries)


class RssCollector:
    def __init__(
        self, client_factory: Callable[[], httpx.Client] | None = None, timeout: float = 20.0
    ) -> None:
        self.client_factory = client_factory or (
            lambda: httpx.Client(timeout=timeout, follow_redirects=True)
        )

    def fetch(self, source: Source) -> FeedResult:
        with self.client_factory() as client:
            response = client.get(source.url, headers={"User-Agent": "newscout"})
            response.raise_for_status()
        result = parse(response.content)
        if not result.entries and not result.title:
            raise FeedError("Not a feed")
        return result
