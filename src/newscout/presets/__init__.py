import json
import sqlite3
from dataclasses import dataclass
from importlib.resources import files

from newscout import db


@dataclass(frozen=True)
class Preset:
    name: str
    relevance: str
    sources: dict[str, str]


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if repeated := {key for key in keys if keys.count(key) > 1}:
        raise ValueError(f"preset repeats {sorted(repeated)}")
    return dict(pairs)


# Every *.json file in this folder is one preset group.
def load() -> tuple[Preset, ...]:
    paths = sorted(
        (path for path in files(__name__).iterdir() if path.name.endswith(".json")),
        key=lambda path: path.name,
    )
    presets = []
    for path in paths:
        item = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
        try:
            presets.append(Preset(**item))
        except TypeError as error:
            raise ValueError(f"{path.name}: {error}") from error
    names = [preset.name for preset in presets]
    if repeated := {name for name in names if names.count(name) > 1}:
        raise ValueError(f"presets repeat the name {sorted(repeated)}")
    # A feed belongs to one group only, so a shared one would go missing from one.
    urls = [url for preset in presets for url in preset.sources]
    if repeated := {url for url in urls if urls.count(url) > 1}:
        raise ValueError(f"presets share the feeds {sorted(repeated)}")
    return tuple(presets)


PRESETS = load()


# Databases from before per-preset tracking stored "1" once these were installed.
LEGACY_PRESETS = ("Turkish News", "Global Finance", "Gaming")


# Old preset names. A group still under its old name takes the new one, so the
# preset is not installed a second time with its sources already taken.
RENAMED = {"Gaming": "Gaming News"}


def _installed(conn: sqlite3.Connection) -> set[str]:
    value = db.settings.get(conn, "presets_installed")
    names = set(LEGACY_PRESETS) if value == "1" else set(value.splitlines() if value else ())
    groups = {group.name: group for group in db.groups.list_all(conn)}
    for old, new in RENAMED.items():
        if old not in names:
            continue
        names = (names - {old}) | {new}
        group = groups.get(old)
        if group and new not in groups:
            db.groups.update(conn, group.id, new, group.relevance)
    return names


def _create(conn: sqlite3.Connection, preset: Preset) -> bool:
    try:
        group_id = db.groups.add(conn, preset.name, preset.relevance)
    except db.groups.DuplicateGroup:
        return False
    db.groups.set_enabled(conn, group_id, False)
    for url, name in preset.sources.items():
        try:
            db.sources.add(conn, url, name=name, group_id=group_id)
        except db.sources.DuplicateSource:
            pass
    return True


# Each preset is installed once, so a new preset shows up on the next run
# while a preset group you delete stays deleted until you restore it.
def install(conn: sqlite3.Connection) -> None:
    installed = _installed(conn)
    for preset in PRESETS:
        if preset.name not in installed:
            installed.add(preset.name)
            _create(conn, preset)
    db.settings.put(conn, "presets_installed", "\n".join(sorted(installed)))


# Presets offered for restoring: no group has the name and some of the feeds are
# gone. A group you renamed but kept the feeds of is not offered again, since
# restoring it would only make an empty group.
def missing(conn: sqlite3.Connection) -> list[Preset]:
    names = {group.name for group in db.groups.list_all(conn)}
    urls = {source.url for source in db.sources.list_all(conn)}
    return [
        preset for preset in PRESETS if preset.name not in names and not set(preset.sources) <= urls
    ]


def restore(conn: sqlite3.Connection, name: str) -> bool:
    preset = next((preset for preset in missing(conn) if preset.name == name), None)
    return preset is not None and _create(conn, preset)
