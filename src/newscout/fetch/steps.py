import logging
import re
from collections.abc import Callable
from dataclasses import replace

from newscout.models import Entry

Step = Callable[[Entry], Entry | None]

log = logging.getLogger(__name__)

_POSTED = re.compile(r"\s*The post .*? appeared first on .*$", re.DOTALL)
_DATE = re.compile(r"^\d{1,2}[./]\d{1,2}[./]\d{4}\s*")


def strip_boilerplate(entry: Entry) -> Entry:
    summary = _POSTED.sub("", entry.summary).strip()
    if entry.title and summary.startswith(entry.title):
        summary = summary[len(entry.title) :].strip()
    summary = _DATE.sub("", summary)
    return entry if summary == entry.summary else replace(entry, summary=summary)


STEPS: list[Step] = [strip_boilerplate]


def apply(entry: Entry, steps: list[Step]) -> Entry | None:
    for step in steps:
        try:
            result = step(entry)
        except Exception:
            log.exception("Step %s failed; skipping it", getattr(step, "__name__", step))
            continue
        if result is None:
            return None
        entry = result
    return entry
