from datetime import UTC, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from newscout import db
from newscout.ai import instructions, state
from newscout.models import FetcherState
from newscout.web.database import conn

bp = Blueprint("control", __name__)

STALE = timedelta(minutes=2)
INTERVALS = (5, 15, 30, 60)
FRESH_OPTIONS = ((30, "30 min"), (60, "1 h"), (360, "6 h"), (1440, "24 h"), (0, "Any time"))


def fetcher_status(state: FetcherState, now: datetime) -> str:
    if state.heartbeat_at is None or now - state.heartbeat_at > STALE:
        return "not responding"
    return "running" if state.running else "stopped"


def ai_status() -> str:
    if not state.judge(conn()):
        return "off"
    if not state.running(conn()):
        return "paused"
    return "problem" if state.problem(conn()) else "on"


@bp.app_context_processor
def states() -> dict:
    fetcher = fetcher_status(db.fetcher.get(conn()), datetime.now(UTC))
    return {"states": {"fetcher": fetcher, "ai": ai_status()}}


def back():
    return redirect(request.referrer or url_for("control.index"))


@bp.get("/control")
def index():
    now = datetime.now(UTC)
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    fetcher = db.fetcher.get(conn())
    ai = state.active(conn())
    counts = db.stories.counts(conn())
    return render_template(
        "control.html",
        state=fetcher,
        status=fetcher_status(fetcher, now),
        interval=db.fetcher.get_interval(conn()),
        next_due=db.fetcher.next_due(conn()),
        stats=db.stats.summary(conn(), since=midnight),
        last_hour=db.stats.count_since(conn(), now - timedelta(hours=1)),
        hourly=db.stats.hourly(conn(), now, hours=24),
        total_sources=len(db.sources.list_all(conn())),
        ai_today=db.stats.statuses_since(conn(), midnight),
        skipped_today=db.stats.skipped_since(conn(), midnight),
        waiting=counts.get("waiting", 0),
        intervals=INTERVALS,
        fresh_minutes=int(db.settings.get(conn(), "fresh_minutes")),
        fresh_options=FRESH_OPTIONS,
        ai=ai,
        key_state="ok"
        if state.tested(conn())
        else "problem"
        if state.problem(conn())
        else "unknown",
        language=instructions.language(conn()),
        custom_instructions=any(
            db.settings.get(conn(), f"ai_{step.key}") for step in instructions.STEPS
        ),
        groups=db.groups.list_all(conn()),
        ai_problem=state.problem(conn()),
    )


@bp.post("/fetcher/start")
def start_fetcher():
    db.fetcher.start(conn())
    return back()


@bp.post("/fetcher/stop")
def stop_fetcher():
    db.fetcher.stop(conn())
    return back()


@bp.post("/fetcher/check")
def check_now():
    db.fetcher.make_due(conn())
    flash("Checking every source now.", "ok")
    return back()


@bp.post("/fetcher/interval")
def interval():
    value = request.form.get("interval", "")
    if value.isdigit() and 1 <= int(value) <= 1440:
        db.fetcher.set_interval(conn(), int(value))
    return back()


@bp.post("/fetcher/freshness")
def freshness():
    value = request.form.get("fresh_minutes", "")
    if value in {str(minutes) for minutes, _ in FRESH_OPTIONS}:
        db.settings.put(conn(), "fresh_minutes", value)
    return back()


@bp.post("/groups/<int:group_id>/toggle")
def toggle_group(group_id: int):
    group = db.groups.get(conn(), group_id)
    if group is not None:
        db.groups.set_enabled(conn(), group_id, not group.enabled)
    return back()


@bp.post("/ai/start")
def start_ai():
    state.set_running(conn(), True)
    return back()


@bp.post("/ai/stop")
def stop_ai():
    state.set_running(conn(), False)
    return back()
