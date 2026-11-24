import pytest

from newscout import db, opml


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


READER_EXPORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
  <head><title>My feeds</title></head>
  <body>
    <outline text="Tech">
      <outline text="The Verge" type="rss" xmlUrl="https://www.theverge.com/rss/index.xml"/>
      <outline text="Deep">
        <outline title="Ars" type="rss" xmlUrl="https://feeds.arstechnica.com/arstechnica/index"/>
      </outline>
    </outline>
    <outline text="Loose" type="rss" xmlUrl="https://example.com/feed"/>
    <outline text="Not a feed" xmlUrl="javascript:alert(1)"/>
  </body>
</opml>"""


def test_a_feed_reader_export_comes_in_as_switched_off_groups(conn):
    result = opml.load(conn, READER_EXPORT)
    assert (result.groups, result.sources, result.skipped) == (2, 3, 0)
    groups = {group.name: group for group in db.groups.list_all(conn)}
    tech = groups["Tech"]
    assert not tech.enabled
    assert {s.name for s in tech.sources} == {"The Verge", "Ars"}
    assert [s.url for s in groups[db.groups.DEFAULT_NAME].sources] == ["https://example.com/feed"]


def test_importing_again_skips_feeds_you_already_have(conn):
    opml.load(conn, READER_EXPORT)
    result = opml.load(conn, READER_EXPORT)
    assert (result.groups, result.sources, result.skipped) == (0, 0, 3)


def test_feeds_join_a_group_with_the_same_name(conn):
    group_id = db.groups.add(conn, "Tech")
    opml.load(conn, READER_EXPORT)
    tech = db.groups.get(conn, group_id)
    assert tech.enabled and len(tech.sources) == 2


def test_export_and_import_keep_groups_names_and_filters(conn, tmp_path):
    group_id = db.groups.add(conn, "Space", "Keep launches & landings <only>.")
    db.sources.add(conn, "https://space.example/rss", name="Space Daily", group_id=group_id)
    data = opml.export(db.groups.list_all(conn)).encode()

    other = db.connect(tmp_path / "other.db")
    opml.load(other, data)
    space = next(g for g in db.groups.list_all(other) if g.name == "Space")
    assert space.relevance == "Keep launches & landings <only>."
    assert [(s.name, s.url) for s in space.sources] == [
        ("Space Daily", "https://space.example/rss")
    ]
    other.close()


@pytest.mark.parametrize(
    "data",
    [b"", b"not xml", b"<rss><channel/></rss>", b"<opml><body/></opml>"],
)
def test_a_file_without_feeds_is_refused(conn, data):
    with pytest.raises(opml.NotOpml):
        opml.load(conn, data)
    assert db.groups.list_all(conn) == []
