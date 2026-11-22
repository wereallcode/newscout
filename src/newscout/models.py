from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Entry:
    guid: str
    title: str
    link: str
    summary: str
    published_at: datetime | None


@dataclass(frozen=True)
class FeedResult:
    title: str | None
    entries: list[Entry]


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    enabled: bool
    relevance: str
    sources: list["Source"]


@dataclass(frozen=True)
class Source:
    id: int
    group_id: int
    type: str
    name: str
    url: str
    enabled: bool
    last_checked_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    failures: int
    next_due_at: datetime | None

    @property
    def status(self) -> str:
        if self.last_error:
            return "error"
        return "ok" if self.last_success_at else "pending"


@dataclass(frozen=True)
class Story:
    id: int
    source_id: int
    source_name: str
    title: str
    link: str
    summary: str
    published_at: datetime | None
    fetched_at: datetime
    sort_at: datetime
    status: str = "waiting"
    reason: str | None = None
    event_id: int | None = None
    relevant: bool = False


@dataclass(frozen=True)
class Event:
    id: int
    title: str
    summary: str
    sort_at: datetime
    sources: list[Story]

    @property
    def merged(self) -> bool:
        return len(self.sources) > 1


@dataclass(frozen=True)
class FetcherState:
    running: bool
    heartbeat_at: datetime | None
    last_pass_at: datetime | None
    last_pass_added: int


@dataclass(frozen=True)
class Stats:
    today: int
    active_sources: int
    failing_sources: int
