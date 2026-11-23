from datetime import UTC, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from newscout import db, presets
from newscout.ai import instructions, state
from newscout.ai.deepseek import check_key
from newscout.web.database import conn
from newscout.web.display import RAW_FILTERS

bp = Blueprint("settings", __name__)

LIMITS = {"new_minutes": 1440, "trash_days": 365, "news_days": 365}
DELETE_AGES = (1, 7, 30)

# Each tab is one group of settings: key -> (label, icon). The first one opens by default.
TABS = {
    "ai": ("AI", "sparkle"),
    "appearance": ("Appearance", "eye"),
    "storage": ("Storage", "database"),
    "presets": ("Presets", "layers"),
}


def tab_of(value: str | None) -> str:
    return value if value in TABS else next(iter(TABS))


def back(tab: str | None = None):
    return redirect(url_for("settings.index", tab=tab_of(tab)))


@bp.get("/settings")
def index():
    values = {name: db.settings.get(conn(), name) for name in LIMITS}
    missing = {preset.name for preset in presets.missing(conn())}
    return render_template(
        "settings.html",
        tab=tab_of(request.args.get("tab")),
        tabs=TABS,
        values=values,
        presets=presets.PRESETS,
        missing=missing,
        steps=instructions.STEPS,
        texts=instructions.load(conn()),
        languages=instructions.LANGUAGES,
        api_keys=state.keys(conn()),
        delete_ages=DELETE_AGES,
        labels={status: label for status, (label, _) in RAW_FILTERS.items() if status != "all"},
        counts=db.stories.counts(conn()),
        key_tested=state.tested(conn()),
        ai_problem=state.problem(conn()),
    )


@bp.post("/settings")
def save():
    tab = request.form.get("tab")
    values = {k: request.form.get(k, "").strip() for k in LIMITS if k in request.form}
    if not values or not all(v.isdigit() and 1 <= int(v) <= LIMITS[k] for k, v in values.items()):
        flash("Enter a number in range.")
        return back(tab)
    for name, value in values.items():
        db.settings.put(conn(), name, value)
    flash("Saved.", "ok")
    return back(tab)


@bp.post("/settings/presets/restore")
def restore_preset():
    name = request.form.get("name", "")
    if presets.restore(conn(), name):
        flash(f"{name} restored. Switch it on in Control Room to start fetching.", "ok")
    else:
        flash("This preset can't be restored.")
    return back("presets")


@bp.post("/settings/ai/language")
def language():
    instructions.set_language(conn(), request.form.get("language", ""))
    return back("ai")


@bp.post("/settings/ai/instructions")
def save_instructions():
    if request.form.get("reset"):
        instructions.save(conn(), {})
        flash("Instructions reset to the defaults.", "ok")
    else:
        instructions.save(conn(), request.form)
        flash("Instructions saved.", "ok")
    return back("ai")


@bp.post("/settings/ai/keys")
def add_key():
    key = request.form.get("api_key", "").strip()
    if key and not key.startswith("sk-"):
        flash("That is not an API key: a DeepSeek key starts with sk-.")
    elif key:
        result = check_key(key)
        if not result.ok:
            flash(result.message)
            return back("ai")
        try:
            state.add_key(conn(), key)
            flash(f"{result.message} It is now the key in use.", "ok")
        except state.DuplicateKey:
            flash("This key is already added.")
    return back("ai")


def key_found(key_id: int) -> str:
    value = state.value_of(conn(), key_id)
    if value is None:
        abort(404)
    return value


@bp.post("/settings/ai/keys/<int:key_id>/use")
def use_key(key_id: int):
    result = check_key(key_found(key_id))
    state.use_key(conn(), key_id, None if result.ok else result.message)
    flash(f"Switched keys. {result.message}", "ok" if result.ok else "")
    return back("ai")


@bp.post("/settings/ai/keys/<int:key_id>/test")
def test_key(key_id: int):
    result = check_key(key_found(key_id))
    if state.key(conn()) == key_found(key_id):
        state.report(conn(), None if result.ok else result.message)
    flash(result.message, "ok" if result.ok else "")
    return back("ai")


@bp.post("/settings/ai/keys/<int:key_id>/delete")
def delete_key(key_id: int):
    key_found(key_id)
    state.remove_key(conn(), key_id)
    flash("Key removed.", "ok")
    return back("ai")


def deleted(count: int):
    flash(f"Deleted {count} raw {'story' if count == 1 else 'stories'}.", "ok")
    return back("storage")


@bp.post("/settings/clean-up/older")
def delete_older():
    days = request.form.get("days", type=int)
    if days not in DELETE_AGES:
        return back("storage")
    return deleted(db.cleanup.delete_older_than(conn(), datetime.now(UTC) - timedelta(days=days)))


@bp.post("/settings/clean-up/label")
def delete_label():
    status = request.form.get("status", "")
    if status not in RAW_FILTERS or status == "all":
        return back("storage")
    return deleted(db.cleanup.delete_status(conn(), status))


@bp.post("/settings/clean-up/all")
def delete_all():
    db.cleanup.clear_all(conn())
    flash("All news deleted and the fetcher paused.", "ok")
    return back("storage")
