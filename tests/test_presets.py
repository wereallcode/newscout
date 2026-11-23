import json

import pytest

from newscout import db, presets


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def test_presets_come_installed_but_not_fetched(conn):
    presets.install(conn)
    groups = {group.name: group for group in db.groups.list_all(conn)}
    for preset in presets.PRESETS:
        group = groups[preset.name]
        assert sorted(s.url for s in group.sources) == sorted(preset.sources)
        assert group.relevance == preset.relevance and not group.enabled


def test_a_deleted_preset_stays_deleted_until_restored(conn):
    presets.install(conn)
    gaming = next(g for g in db.groups.list_all(conn) if g.name == "Gaming News")
    db.groups.delete(conn, gaming.id)
    presets.install(conn)
    assert "Gaming News" not in {g.name for g in db.groups.list_all(conn)}
    assert [p.name for p in presets.missing(conn)] == ["Gaming News"]
    assert presets.restore(conn, "Gaming News")
    groups = {g.name: g for g in db.groups.list_all(conn)}
    preset = next(p for p in presets.PRESETS if p.name == "Gaming News")
    assert sorted(s.url for s in groups["Gaming News"].sources) == sorted(preset.sources)
    assert not groups["Gaming News"].enabled
    assert presets.missing(conn) == []


def test_restore_ignores_unknown_and_present_presets(conn):
    presets.install(conn)
    assert not presets.restore(conn, "Gaming News")
    assert not presets.restore(conn, "Nope")


def test_a_renamed_preset_group_is_not_offered_again(conn):
    presets.install(conn)
    gaming = next(g for g in db.groups.list_all(conn) if g.name == "Gaming News")
    db.groups.update(conn, gaming.id, "Oyun", gaming.relevance)
    assert presets.missing(conn) == []
    assert not presets.restore(conn, "Gaming News")
    assert "Gaming News" not in {g.name for g in db.groups.list_all(conn)}


def test_install_keeps_groups_you_already_have(conn):
    mine = db.groups.add(conn, "Gaming News", "Only Nintendo.")
    presets.install(conn)
    assert db.groups.get(conn, mine).relevance == "Only Nintendo."
    assert len([g for g in db.groups.list_all(conn) if g.name == "Gaming News"]) == 1


def test_a_new_preset_reaches_an_existing_install(conn, monkeypatch):
    first, *rest = presets.PRESETS
    monkeypatch.setattr(presets, "PRESETS", (first,))
    presets.install(conn)
    monkeypatch.setattr(presets, "PRESETS", (first, *rest))
    presets.install(conn)
    names = {g.name for g in db.groups.list_all(conn)}
    assert {p.name for p in presets.PRESETS} <= names


def test_installs_from_before_per_preset_tracking_get_only_new_presets(conn):
    db.settings.put(conn, "presets_installed", "1")
    presets.install(conn)
    assert [g.name for g in db.groups.list_all(conn)] == ["World News"]


def test_a_renamed_preset_renames_your_group_instead_of_adding_one(conn):
    old = db.groups.add(conn, "Gaming", "Only Nintendo.")
    db.sources.add(conn, "https://www.ign.com/rss/articles/feed", group_id=old)
    db.settings.put(conn, "presets_installed", "Gaming\nGlobal Finance\nTurkish News")
    presets.install(conn)
    assert [(g.name, g.relevance) for g in db.groups.list_all(conn)] == [
        ("Gaming News", "Only Nintendo."),
        ("World News", next(p.relevance for p in presets.PRESETS if p.name == "World News")),
    ]
    assert presets.missing(conn) == []


def test_removed_presets_leave_your_groups_alone(conn):
    old = db.groups.add(conn, "Global Finance", "Markets.")
    db.settings.put(conn, "presets_installed", "1")
    presets.install(conn)
    assert db.groups.get(conn, old).name == "Global Finance"
    assert {p.name for p in presets.missing(conn)} == {"Gaming News"}


def test_each_json_file_is_a_preset():
    assert {p.name for p in presets.PRESETS} == {"Gaming News", "World News"}


def test_presets_must_not_share_a_feed(tmp_path, monkeypatch):
    preset = {"name": "A", "relevance": "", "sources": {"https://x.test/feed": "X"}}
    (tmp_path / "a.json").write_text(json.dumps(preset))
    (tmp_path / "b.json").write_text(json.dumps({**preset, "name": "B"}))
    monkeypatch.setattr(presets, "files", lambda _name: tmp_path)
    with pytest.raises(ValueError, match="share the feeds"):
        presets.load()
