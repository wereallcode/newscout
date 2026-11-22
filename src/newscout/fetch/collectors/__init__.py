from newscout.fetch.collectors.base import Collector, FeedError
from newscout.fetch.collectors.rss import RssCollector

COLLECTORS: dict[str, Collector] = {"rss": RssCollector()}

__all__ = ["COLLECTORS", "Collector", "FeedError"]
