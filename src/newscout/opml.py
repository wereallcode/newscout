import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from newscout import db
from newscout.models import Group

NAMESPACE = "urn:newscout"
FILTER = f"{{{NAMESPACE}}}filter"
MAX_GROUP_NAME = 40

ET.register_namespace("newscout", NAMESPACE)


class NotOpml(Exception):
    pass


@dataclass
class Folder:
    name: str
    filter: str = ""
    feeds: dict[str, str] = field(default_factory=dict)


@dataclass
class Imported:
    groups: int = 0
    sources: int = 0
    skipped: int = 0


def export(groups: list[Group]) -> str:
    root = ET.Element("opml", version="2.0")
    ET.SubElement(ET.SubElement(root, "head"), "title").text = "Newscout sources"
    body = ET.SubElement(root, "body")
    for group in groups:
        folder = ET.SubElement(body, "outline", text=group.name, title=group.name)
        if group.relevance:
            folder.set(FILTER, group.relevance)
        for source in group.sources:
            ET.SubElement(
                folder,
                "outline",
                type="rss",
                text=source.name,
                title=source.name,
                xmlUrl=source.url,
            )
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def _feeds(outline: ET.Element) -> dict[str, str]:
    feeds = {}
    for item in outline.iter("outline"):
        url = (item.get("xmlUrl") or "").strip()
        if url.startswith(("http://", "https://")):
            feeds.setdefault(url, (item.get("title") or item.get("text") or "").strip())
    return feeds


def parse(data: bytes) -> list[Folder]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise NotOpml from error
    body = root.find("body")
    if root.tag != "opml" or body is None:
        raise NotOpml
    folders: dict[str, Folder] = {}
    loose = Folder(db.groups.DEFAULT_NAME)
    for outline in body.findall("outline"):
        if outline.get("xmlUrl"):
            loose.feeds.update(_feeds(outline))
            continue
        name = " ".join((outline.get("title") or outline.get("text") or "").split())
        name = name[:MAX_GROUP_NAME] or "Untitled"
        folder = folders.setdefault(name, Folder(name))
        folder.filter = folder.filter or (outline.get(FILTER) or "").strip()
        folder.feeds.update(_feeds(outline))
    found = [folder for folder in [loose, *folders.values()] if folder.feeds]
    if not found:
        raise NotOpml
    return found


def load(conn: sqlite3.Connection, data: bytes) -> Imported:
    result = Imported()
    folders = parse(data)
    groups = {group.name: group.id for group in db.groups.list_all(conn)}
    known = {source.url for source in db.sources.list_all(conn)}
    for folder in folders:
        for url, name in folder.feeds.items():
            if url in known:
                result.skipped += 1
                continue
            if folder.name not in groups:
                groups[folder.name] = db.groups.add(conn, folder.name, folder.filter)
                db.groups.set_enabled(conn, groups[folder.name], False)
                result.groups += 1
            db.sources.add(conn, url, name=name or None, group_id=groups[folder.name])
            known.add(url)
            result.sources += 1
    return result
