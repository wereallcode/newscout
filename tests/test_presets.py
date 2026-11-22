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


def test_a_deleted_preset_stays_deleted(conn):
    presets.install(conn)
    gaming = next(g for g in db.groups.list_all(conn) if g.name == "Gaming")
    db.groups.delete(conn, gaming.id)
    presets.install(conn)
    assert "Gaming" not in {g.name for g in db.groups.list_all(conn)}


def test_install_keeps_groups_you_already_have(conn):
    mine = db.groups.add(conn, "Gaming", "Only Nintendo.")
    presets.install(conn)
    assert db.groups.get(conn, mine).relevance == "Only Nintendo."
    assert len([g for g in db.groups.list_all(conn) if g.name == "Gaming"]) == 1
