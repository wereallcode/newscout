from flask import Blueprint, flash, redirect, render_template, request, url_for

from newscout import db
from newscout.web.database import conn

bp = Blueprint("settings", __name__)

LIMITS = {"new_minutes": 1440, "trash_days": 365, "news_days": 365}


def back():
    return redirect(url_for("settings.index"))


@bp.get("/settings")
def index():
    values = {name: db.settings.get(conn(), name) for name in LIMITS}
    return render_template("settings.html", values=values)


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
