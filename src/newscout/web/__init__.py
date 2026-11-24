import os
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, request

from newscout import auth, db
from newscout.web import database, display
from newscout.web.views import control, dashboard, security, settings, sources


def same_site_only() -> None:
    origin = request.headers.get("Origin")
    if request.method == "POST" and origin and urlparse(origin).netloc != request.host:
        abort(403)


def secret_key(path: Path) -> str:
    conn = db.connect(path)
    try:
        return auth.secret(conn)
    finally:
        conn.close()


def create_app(path: Path | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = path or db.default_path()
    app.secret_key = os.environ.get("NEWSCOUT_SECRET") or secret_key(app.config["DATABASE"])
    app.config["SESSION_COOKIE_NAME"] = "newscout"
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.jinja_env.filters.update(
        ago=display.ago,
        when=display.ago_or_in,
        hue=display.hue,
        host=display.host,
        status_label=display.STATUS_LABELS.get,
        source_label=display.SOURCE_LABELS.get,
        health_label=display.HEALTH_LABELS.get,
    )
    app.before_request(same_site_only)
    app.before_request(security.require_login)
    app.teardown_appcontext(database.close)
    for view in (dashboard, control, settings, security, sources):
        app.register_blueprint(view.bp)
    return app
