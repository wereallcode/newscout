from flask import Blueprint, flash, redirect, render_template, request, url_for

from newscout import db, presets
from newscout.web.database import conn

bp = Blueprint("settings", __name__)

LIMITS = {"new_minutes": 1440, "trash_days": 365, "news_days": 365}


def back():
    return redirect(url_for("settings.index"))


@bp.get("/settings")
def index():
    values = {name: db.settings.get(conn(), name) for name in LIMITS}
    missing = {preset.name for preset in presets.missing(conn())}
    return render_template("settings.html", values=values, presets=presets.PRESETS, missing=missing)


@bp.post("/settings")
def save():
    values = {k: request.form.get(k, "").strip() for k in LIMITS if k in request.form}
    if not values or not all(v.isdigit() and 1 <= int(v) <= LIMITS[k] for k, v in values.items()):
        flash("Enter a number in range.")
        return back()
    for name, value in values.items():
        db.settings.put(conn(), name, value)
    flash("Saved.", "ok")
    return back()


@bp.post("/settings/presets/restore")
def restore_preset():
    name = request.form.get("name", "")
    if presets.restore(conn(), name):
        flash(f"{name} restored. Switch it on in Control Room to start fetching.", "ok")
    else:
        flash("This preset can't be restored.")
    return back()
