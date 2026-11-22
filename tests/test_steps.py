from dataclasses import replace

from newscout.fetch.steps import apply
from newscout.models import Entry

ENTRY = Entry(guid="a", title="hello", link="", summary="", published_at=None)


def boom(entry):
    raise RuntimeError("broken step")


def upper_title(entry):
    return replace(entry, title=entry.title.upper())


def test_failing_step_is_skipped():
    assert apply(ENTRY, [boom, upper_title]).title == "HELLO"


def test_step_returning_none_drops_entry():
    assert apply(ENTRY, [lambda entry: None, upper_title]) is None
