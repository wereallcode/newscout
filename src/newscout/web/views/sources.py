from urllib.parse import urlparse

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from newscout import db
from newscout.ai.instructions import RELEVANCE
from newscout.web.database import conn

bp = Blueprint("sources", __name__)


def valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def found(source_id: int):
    source = db.sources.get(conn(), source_id)
    if source is None:
        abort(404)
    return source


def back():
    return redirect(url_for("sources.index"))


@bp.get("/sources")
def index():
    groups = db.groups.list_all(conn())
    return render_template("sources.html", groups=groups, relevance_default=RELEVANCE)


@bp.post("/sources")
def add():
    url = request.form.get("url", "").strip()
    group = db.groups.get(conn(), request.form.get("group_id", 0, type=int))
    if not valid_url(url):
        flash("Enter a valid URL.")
    else:
        try:
            db.sources.add(conn(), url, group_id=group.id if group else None)
        except db.sources.DuplicateSource:
            flash("Already added.")
    return back()


@bp.post("/sources/<int:source_id>/toggle")
def toggle(source_id: int):
    db.sources.set_enabled(conn(), source_id, not found(source_id).enabled)
    return back()


@bp.post("/sources/<int:source_id>/retry")
def retry(source_id: int):
    found(source_id)
    db.fetcher.make_due(conn(), source_id)
    flash("Checking again on the next pass.", "ok")
    return back()


@bp.post("/sources/<int:source_id>/delete")
def delete(source_id: int):
    found(source_id)
    db.sources.delete(conn(), source_id)
    return back()


def group_found(group_id: int):
    group = db.groups.get(conn(), group_id)
    if group is None:
        abort(404)
    return group


def group_name() -> str:
    return " ".join(request.form.get("name", "").split())[:40]


@bp.post("/groups")
def add_group():
    name = group_name()
    try:
        if name:
            db.groups.add(conn(), name)
    except db.groups.DuplicateGroup:
        flash("A group with this name already exists.")
    return back()


@bp.post("/groups/<int:group_id>")
def update_group(group_id: int):
    group_found(group_id)
    relevance = request.form.get("relevance", "").strip()
    try:
        db.groups.update(
            conn(),
            group_id,
            group_name() or "Untitled",
            "" if relevance == RELEVANCE else relevance,
        )
        flash("Group saved.", "ok")
    except db.groups.DuplicateGroup:
        flash("A group with this name already exists.")
    return back()


@bp.post("/groups/<int:group_id>/delete")
def delete_group(group_id: int):
    group = group_found(group_id)
    db.groups.delete(conn(), group_id)
    flash(f"{group.name} and its sources deleted.", "ok")
    return back()
