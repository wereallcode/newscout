from typing import Protocol

from newscout.models import FeedResult, Source


class FeedError(Exception):
    pass


class Collector(Protocol):
    def fetch(self, source: Source) -> FeedResult: ...
