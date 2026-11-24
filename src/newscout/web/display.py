from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

STATUS_LABELS = {"running": "Running", "stopped": "Paused", "not responding": "Not Working"}
HEALTH_LABELS = {"ok": "Active", "problem": "Not Working", "unknown": "Not Tested"}
SOURCE_LABELS = {"ok": "Working", "error": "Problem", "pending": "Waiting"}
RAW_FILTERS = {
    "all": ("All", ("waiting", "kept", "merged", "dropped", "trash")),
    "waiting": ("Waiting", ("waiting",)),
    "kept": ("News", ("kept",)),
    "merged": ("Merged", ("merged",)),
    "dropped": ("Dropped", ("dropped",)),
    "trash": ("Trash", ("trash",)),
}
HUES = (245, 190, 150, 25, 330, 280, 205, 95)


def ago(value: datetime | None) -> str:
    if value is None:
        return "never"
    seconds = max(0, int((datetime.now(UTC) - value).total_seconds()))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return "now"


def ago_or_in(value: datetime | None) -> str:
    now = datetime.now(UTC)
    if value is None or value - now < timedelta(minutes=1):
        return "now"
    return "in " + ago(now - (value - now))


def host(url: str) -> str:
    name = urlparse(url).hostname or url
    return name.removeprefix("www.")


def hue(source_id: int) -> int:
    return HUES[(source_id - 1) % len(HUES)]
