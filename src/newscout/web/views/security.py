from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from newscout import auth
from newscout.web.database import conn

bp = Blueprint("security", __name__)

OPEN = ("security.login", "security.sign_in", "static")


def require_login():
    if request.endpoint in OPEN or not auth.enabled(conn()):
        return None
    if session.get("token") == auth.token(conn()):
        return None
    return redirect(url_for("security.login"), 303)


def verified(field: str) -> bool:
    try:
        if auth.verify(conn(), request.form.get(field, "")):
            return True
        flash("Wrong password.")
    except auth.TooManyAttempts:
        flash(f"Too many attempts. Wait {auth.WAIT_SECONDS} seconds.")
    return False


def remember() -> None:
    session.clear()
    session.permanent = True
    session["token"] = auth.token(conn())


def back():
    return redirect(url_for("settings.index", tab="auth"))


@bp.get("/login")
def login():
    if not auth.enabled(conn()) or session.get("token") == auth.token(conn()):
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@bp.post("/login")
def sign_in():
    if not auth.enabled(conn()):
        return redirect(url_for("dashboard.index"))
    if not verified("password"):
        return redirect(url_for("security.login"))
    remember()
    return redirect(url_for("dashboard.index"))


@bp.post("/settings/auth/sign-out")
def sign_out():
    session.clear()
    return redirect(url_for("security.login"))


@bp.post("/settings/auth/password")
def save_password():
    password = request.form.get("new", "")
    if len(password) < auth.MIN_LENGTH:
        flash(f"Use at least {auth.MIN_LENGTH} characters.")
    elif password != request.form.get("repeat"):
        flash("The passwords do not match.")
    elif not auth.enabled(conn()) or verified("current"):
        auth.set_password(conn(), password)
        remember()
        flash("Password saved.", "ok")
    return back()


@bp.post("/settings/auth/password/remove")
def remove_password():
    if auth.enabled(conn()) and verified("current"):
        auth.remove_password(conn())
        session.clear()
        flash("Password removed.", "ok")
    return back()
