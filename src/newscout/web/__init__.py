import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, request

from newscout import db
from newscout.web import database, display
from newscout.web.views import control, dashboard, settings, sources


def same_site_only() -> None:
    # No login yet, so refuse form posts that another website makes in your browser.
    origin = request.headers.get("Origin")
    if request.method == "POST" and origin and urlparse(origin).netloc != request.host:
        abort(403)


def create_app(path: Path | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("NEWSCOUT_SECRET") or secrets.token_hex(16)
    app.config["DATABASE"] = path or db.default_path()
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # an OPML upload is the largest request
    app.jinja_env.filters.update(
        ago=display.ago,
        when=display.ago_or_in,
        hue=display.hue,
        host=display.host,
        status_label=display.STATUS_LABELS.get,
        source_label=display.SOURCE_LABELS.get,
    )
    app.before_request(same_site_only)
    app.teardown_appcontext(database.close)
    for view in (dashboard, control, settings, sources):
        app.register_blueprint(view.bp)
    return app
