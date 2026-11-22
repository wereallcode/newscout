import pytest

from newscout import __main__ as cli


def test_unknown_command_exits_2():
    with pytest.raises(SystemExit) as error:
        cli.main(["nope"])
    assert error.value.code == 2


def test_fetch_command_runs_the_fetcher(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("NEWSCOUT_DB", str(tmp_path / "x.db"))
    monkeypatch.setattr(cli, "run_forever", lambda path, stop: calls.append("fetcher"))
    monkeypatch.setattr(cli, "start", lambda loop, path, stop: calls.append(loop.__name__))
    assert cli.main(["fetch"]) == 0
    assert calls == ["run_ai", "fetcher"]


def test_dev_command_starts_with_the_fetcher_and_ai_paused(monkeypatch, tmp_path):
    from newscout import db

    path = tmp_path / "x.db"
    monkeypatch.setenv("NEWSCOUT_DB", str(path))
    db.fetcher.start(db.connect(path))
    db.settings.put(db.connect(path), "ai_running", "1")
    monkeypatch.setattr(cli, "start", lambda loop, path, stop: None)
    monkeypatch.setattr("flask.Flask.run", lambda self, **kwargs: None)
    assert cli.main([]) == 0
    assert db.fetcher.get(db.connect(path)).running is False
    assert not db.settings.get(db.connect(path), "ai_running")


def test_fetch_command_keeps_the_fetcher_state(monkeypatch, tmp_path):
    from newscout import db

    path = tmp_path / "x.db"
    monkeypatch.setenv("NEWSCOUT_DB", str(path))
    db.fetcher.start(db.connect(path))
    monkeypatch.setattr(cli, "run_forever", lambda path, stop: None)
    monkeypatch.setattr(cli, "start", lambda loop, path, stop: None)
    cli.main(["fetch"])
    assert db.fetcher.get(db.connect(path)).running is True
