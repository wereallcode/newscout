from datetime import UTC, datetime, timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from newscout import db
from newscout.ai import instructions
from newscout.web.database import conn
from newscout.web.display import RAW_FILTERS

bp = Blueprint("dashboard", __name__)

PAGE_SIZE = 50
TABS = {
    "raw": {"name": "Raw", "empty": "New raw news shows up here as it arrives."},
    "newsroom": {"name": "Newsroom", "empty": "The AI turns raw news into news here."},
}


def page_of(total: int) -> tuple[int, int]:
    pages = max(1, -(-total // PAGE_SIZE))
    return min(max(request.args.get("page", 1, type=int) or 1, 1), pages), pages


def back(tab: str | None = None):
    return redirect(request.referrer or url_for("dashboard.index", step=tab))


@bp.get("/")
def index():
    tab = request.args.get("step", "newsroom")
    if tab not in TABS:
        tab = "newsroom"
    raw = db.stories.counts(conn())
    counts = {key: sum(raw.get(s, 0) for s in group) for key, (_, group) in RAW_FILTERS.items()}
    show = request.args.get("show", "all")
    if show not in RAW_FILTERS:
        show = "all"
    news_count = db.news.count(conn())
    if tab == "raw":
        page, pages = page_of(counts[show])
        items = db.stories.list_raw(conn(), PAGE_SIZE, (page - 1) * PAGE_SIZE, RAW_FILTERS[show][1])
    else:
        page, pages = page_of(news_count)
        items = db.news.list_page(conn(), PAGE_SIZE, (page - 1) * PAGE_SIZE)
    new_minutes = int(db.settings.get(conn(), "new_minutes"))
    return render_template(
        "dashboard.html",
        items=items,
        new_since=datetime.now(UTC) - timedelta(minutes=new_minutes),
        page=page,
        pages=pages,
        step=tab,
        tabs=TABS,
        show=show,
        filters=RAW_FILTERS,
        counts=counts,
        news_count=news_count,
        has_sources=bool(db.sources.list_all(conn())),
        steps=instructions.STEPS,
        texts=instructions.load(conn()),
    )


@bp.post("/instructions")
def save_instructions():
    if request.form.get("reset"):
        instructions.save(conn(), {})
        flash("Instructions reset to the defaults.", "ok")
    else:
        instructions.save(conn(), request.form)
        flash("Instructions saved.", "ok")
    return redirect(url_for("dashboard.index", step="raw"))


def found(story_id: int) -> None:
    if db.stories.get(conn(), story_id) is None:
        abort(404)


@bp.post("/stories/<int:story_id>/trash")
def trash_story(story_id: int):
    found(story_id)
    db.stories.set_status(conn(), story_id, "trash", "Trashed by you")
    return back("raw")


@bp.post("/stories/<int:story_id>/restore")
def restore_story(story_id: int):
    found(story_id)
    db.stories.restore(conn(), story_id)
    return back("raw")


@bp.post("/events/<int:event_id>/trash")
def trash_event(event_id: int):
    if db.news.get(conn(), event_id) is None:
        abort(404)
    db.news.trash(conn(), event_id)
    return back()


@bp.get("/api/latest")
def latest():
    table = "stories" if request.args.get("tab") == "raw" else "events"
    newest = db.stats.latest_id(conn(), table)
    since = request.args.get("since", type=int)
    if since is None:
        return jsonify(latest=newest)
    return jsonify(latest=newest, new=db.stats.count_after(conn(), table, since))
