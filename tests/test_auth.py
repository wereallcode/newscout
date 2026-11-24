import pytest

from newscout import __main__ as cli
from newscout import auth, db
from newscout.web import create_app

PASSWORD = "correct horse"
NEW = "battery staple"


@pytest.fixture
def path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(path):
    connection = db.connect(path)
    yield connection
    connection.close()


@pytest.fixture
def app(path):
    return create_app(path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def locked(conn):
    auth.set_password(conn, PASSWORD)


def sign_in(client, password=PASSWORD):
    return client.post("/login", data={"password": password})


def change(client, new=NEW, repeat=None, current=PASSWORD):
    data = {"current": current, "new": new, "repeat": repeat or new}
    return client.post("/settings/auth/password", data=data, follow_redirects=True)


def test_open_without_a_password(client):
    assert client.get("/").status_code == 200
    assert client.get("/login").location == "/"
    assert sign_in(client).location == "/"


def test_every_route_needs_login(app, client, locked):
    for rule in app.url_map.iter_rules():
        if rule.endpoint in ("static", "security.login", "security.sign_in"):
            continue
        url = rule.rule.replace("<int:", "<")
        while "<" in url:
            url = url[: url.index("<")] + "1" + url[url.index(">") + 1 :]
        method = "POST" if "POST" in rule.methods else "GET"
        assert client.open(url, method=method).location == "/login", url


def test_login_page_and_styles_are_public(client, locked):
    page = client.get("/login")
    assert page.status_code == 200
    assert "control-bar" not in page.text
    assert client.get("/static/style.css").status_code == 200


def test_sign_in_and_out(client, locked):
    assert sign_in(client).location == "/"
    assert client.get("/").status_code == 200
    client.post("/settings/auth/sign-out")
    assert client.get("/").location == "/login"


def test_wrong_password(client, locked):
    assert sign_in(client, "nope").location == "/login"
    assert "Wrong password." in client.get("/login").text
    assert client.get("/").location == "/login"


def test_too_many_attempts_block_even_the_right_password(client, locked, monkeypatch):
    for _ in range(auth.FREE_ATTEMPTS):
        sign_in(client, "nope")
    assert sign_in(client).location == "/login"
    assert "Too many attempts" in client.get("/login").text
    now = auth.time.time()
    monkeypatch.setattr(auth.time, "time", lambda: now + auth.WAIT_SECONDS + 1)
    assert sign_in(client).location == "/"


def test_signing_in_clears_the_attempts(client, conn, locked):
    sign_in(client, "nope")
    sign_in(client)
    assert db.settings.get(conn, "login_attempts") is None


def test_first_password_keeps_you_signed_in(client, conn):
    assert "Password saved." in change(client, PASSWORD).text
    assert auth.enabled(conn)
    assert client.get("/").status_code == 200


def test_short_or_different_passwords_are_refused(client, conn):
    assert "at least 8" in change(client, "short").text
    assert "do not match" in change(client, NEW, "something else").text
    assert not auth.enabled(conn)


def test_changing_needs_the_current_password_and_ends_other_sessions(app, client, locked):
    other = app.test_client()
    sign_in(client)
    sign_in(other)
    assert "Wrong password." in change(client, current="nope").text
    assert other.get("/").status_code == 200
    assert "Password saved." in change(client).text
    assert client.get("/").status_code == 200
    assert other.get("/").location == "/login"


def test_removing_needs_the_current_password(client, conn, locked):
    sign_in(client)
    client.post("/settings/auth/password/remove", data={"current": "nope"})
    assert auth.enabled(conn)
    client.post("/settings/auth/password/remove", data={"current": PASSWORD})
    assert not auth.enabled(conn)
    assert client.get("/").status_code == 200


def test_sessions_survive_a_restart(app, client, path, locked):
    sign_in(client)
    cookie = client.get_cookie("newscout")
    again = create_app(path).test_client()
    again.set_cookie("newscout", cookie.value)
    assert again.get("/").status_code == 200


def test_password_is_stored_hashed(conn, locked):
    assert PASSWORD not in db.settings.get(conn, "password")


def test_reset_password_command(conn, path, locked, monkeypatch):
    monkeypatch.setenv("NEWSCOUT_DB", str(path))
    assert cli.main(["reset-password"]) == 0
    assert not auth.enabled(conn)


def test_auth_tab(client, locked):
    sign_in(client)
    page = client.get("/settings?tab=auth").text
    for text in ("Current Password", "Sign Out", "Remove Password"):
        assert text in page


def test_sign_out_shows_only_with_a_password(client, conn):
    assert "Sign Out" not in client.get("/settings").text
    auth.set_password(conn, PASSWORD)
    sign_in(client)
    assert "Sign Out" in client.get("/settings").text
