import json
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from newscout import db
from newscout.ai import instructions, local, loop, pipeline, similarity, state
from newscout.ai.deepseek import DeepSeekJudge, KeyCheck, check_key
from newscout.ai.pipeline import Draft, Verdict
from newscout.models import Entry

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
DRAFT = Draft("Clean title", "Clean summary")
TEXTS = {"merge": "Same event only.", "rewrite": "Be brief."}


@pytest.fixture
def path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(path):
    connection = db.connect(path)
    yield connection
    connection.close()


def raw(conn, url, title, summary="", when=NOW):
    source = db.sources.add(conn, url)
    db.stories.save(conn, source, [Entry(title, title, "", summary, when)], when)
    return db.stories.list_raw(conn, statuses=("waiting",))[0]


def news(conn, url, title, when=NOW):
    story = raw(conn, url, title, when=when)
    return db.stories.keep(conn, story.id, title, "")


class Judge:
    """Stands in for DeepSeek and records every question it gets."""

    def __init__(self, relevant=True, match=None, draft=DRAFT):
        self.answers = {"relevant": relevant, "match": match, "draft": draft}
        self.calls = []

    def _answer(self, name):
        answer = self.answers[name]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def relevant(self, story, text):
        self.calls.append(("relevant", story.title, text))
        answer = self._answer("relevant")
        return answer if isinstance(answer, Verdict) else Verdict(answer, "off topic")

    def match(self, story, candidates, text):
        self.calls.append(("match", [c.title for c in candidates], text))
        answer = self._answer("match")
        return answer(candidates) if callable(answer) else answer

    def rewrite(self, stories, text):
        self.calls.append(("rewrite", [s.title for s in stories], text))
        return self._answer("draft")


def steps(judge):
    return [call[0] for call in judge.calls]


def test_similar_titles_are_candidates_and_unrelated_are_not():
    assert similarity.similarity("Güngören'de temel kazısında göçük", "Güngören'de göçük") > 0.2
    assert similarity.similarity("Güngören'de göçük", "Real Madrid Bayern'i geçti") == 0


def test_turkish_letters_are_compared_case_insensitively():
    assert similarity.similarity("İSTANBUL'DA YAĞIŞ", "istanbul'da yağış") == 1


def test_relevant_story_is_rewritten_into_news(conn):
    story = raw(conn, "https://a.example/feed", "Ham başlık")
    group = db.sources.get(conn, story.source_id).group_id
    db.groups.update(conn, group, "Ankara", "Only Ankara news.")
    judge = Judge()
    assert pipeline.process(conn, judge, TEXTS) == 1
    (event,) = db.news.list_page(conn)
    assert (event.title, event.summary) == ("Clean title", "Clean summary")
    assert steps(judge) == ["relevant", "rewrite"]
    assert judge.calls[0][2] == "Only Ankara news." and judge.calls[1][2].startswith("Be brief.\n")
    assert db.stories.counts(conn) == {"kept": 1}


def test_irrelevant_story_is_dropped_with_the_reason(conn):
    raw(conn, "https://a.example/feed", "Derbi sonucu")
    judge = Judge(relevant=False)
    pipeline.process(conn, judge, TEXTS)
    assert steps(judge) == ["relevant"]
    (story,) = db.stories.list_raw(conn, statuses=("dropped",))
    assert story.reason == "off topic"


def test_same_event_is_merged_and_rewritten_from_every_source(conn):
    target = news(conn, "https://ntv.example/feed", "Temel kazısında toprak kayması")
    raw(conn, "https://sozcu.example/feed", "Güngören'de temel kazısı sırasında göçük")
    judge = Judge(match=lambda options: options[0].id, draft=Draft("Güngören'de göçük", "Özet"))
    pipeline.process(conn, judge, TEXTS)
    assert steps(judge) == ["relevant", "match", "rewrite"]
    assert judge.calls[1][2] == "Same event only."
    assert len(judge.calls[2][1]) == 2
    (event,) = db.news.list_page(conn)
    assert event.id == target and event.merged and event.title == "Güngören'de göçük"
    assert db.stories.counts(conn) == {"kept": 1, "merged": 1}


def test_no_candidates_skips_the_merge_question(conn):
    news(conn, "https://a.example/feed", "Real Madrid Bayern'i geçti")
    raw(conn, "https://b.example/feed", "Ankara'da sağanak yağış")
    judge = Judge()
    pipeline.process(conn, judge, TEXTS)
    assert "match" not in steps(judge)


def test_unknown_match_becomes_new_news(conn):
    news(conn, "https://a.example/feed", "Ankara'da sağanak yağış")
    raw(conn, "https://b.example/feed", "Ankara'da sağanak yağış sürüyor")
    pipeline.process(conn, Judge(match=999), TEXTS)
    assert db.news.count(conn) == 2


def test_only_similar_recent_untrashed_news_are_offered(conn):
    news(conn, "https://a.example/feed", "Ankara'da sağanak yağış", when=NOW - timedelta(days=3))
    trashed = news(conn, "https://b.example/feed", "Ankara'da sağanak yağış başladı")
    db.news.trash(conn, trashed)
    news(conn, "https://c.example/feed", "Real Madrid Bayern'i geçti")
    story = raw(conn, "https://d.example/feed", "Ankara'da sağanak yağış sürüyor")
    assert similarity.candidates(conn, story) == []


def test_relevant_story_stays_waiting_when_a_later_step_fails(conn):
    raw(conn, "https://a.example/feed", "Ankara'da sağanak yağış")
    judge = Judge(draft=RuntimeError("offline"))
    with pytest.raises(RuntimeError):
        pipeline.process(conn, judge, TEXTS)
    (story,) = db.stories.list_raw(conn, statuses=("waiting",))
    assert story.relevant
    judge = Judge()
    pipeline.process(conn, judge, TEXTS)
    assert steps(judge) == ["rewrite"]


def test_restored_story_skips_the_relevance_check(conn):
    story = raw(conn, "https://a.example/feed", "Derbi sonucu")
    pipeline.process(conn, Judge(relevant=False), TEXTS)
    db.stories.restore(conn, story.id)
    judge = Judge(relevant=False)
    pipeline.process(conn, judge, TEXTS)
    assert steps(judge) == ["rewrite"] and db.news.count(conn) == 1


def test_instructions_fall_back_to_the_defaults(conn):
    defaults = {step.key: step.default for step in instructions.STEPS} | {"language": ""}
    assert instructions.load(conn) == defaults
    instructions.save(conn, {"merge": "Same day only.", "rewrite": defaults["rewrite"]})
    assert instructions.load(conn) == defaults | {"merge": "Same day only."}
    assert db.settings.get(conn, "ai_rewrite") is None
    instructions.save(conn, {})
    assert instructions.load(conn) == defaults


def test_chosen_language_is_added_to_the_rewrite_instruction(conn):
    raw(conn, "https://a.example/feed", "Markets fall")
    judge = Judge()
    pipeline.process(conn, judge, TEXTS | {"language": "Turkish"})
    assert judge.calls[-1][2].endswith(
        "Write the title and summary in Turkish, whatever language the sources use."
    )


def test_news_in_another_language_is_matched_by_its_source_titles(conn):
    event = news(conn, "https://a.example/feed", "Fed raises interest rates again")
    db.stories.attach(
        conn, db.news.get(conn, event).sources[0].id, event, "Fed faizi yine artırdı", ""
    )
    story = raw(conn, "https://b.example/feed", "Fed raises interest rates by a quarter point")
    assert [e.id for e in similarity.candidates(conn, story)] == [event]


def test_each_group_has_its_own_relevance(conn):
    finance = db.groups.add(conn, "Finance", "Only markets.")
    mine = db.sources.add(conn, "https://a.example/feed")
    markets = db.sources.add(conn, "https://b.example/feed", group_id=finance)
    assert instructions.relevance(conn, mine) == instructions.RELEVANCE
    assert instructions.relevance(conn, markets) == "Only markets."


def deepseek(content):
    seen = []

    def handler(request):
        seen.append((request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = lambda: httpx.Client(transport=httpx.MockTransport(handler))  # noqa: E731
    return DeepSeekJudge("sk-test", client_factory=client), seen


def test_deepseek_asks_each_step_with_its_instructions(conn):
    target = news(conn, "https://a.example/feed", "Ankara'da sağanak yağış")
    story = raw(conn, "https://b.example/feed", "Ankara'da sağanak yağış sürüyor")
    judge, seen = deepseek('{"relevant": true}')
    assert judge.relevant(story, "Only Ankara news.") == Verdict(True)
    judge, seen = deepseek(f'{{"match": {target}}}')
    assert judge.match(story, [db.news.get(conn, target)], "Same event.") == target
    auth, body = seen[0]
    system, user = body["messages"]
    assert auth == "Bearer sk-test" and system["content"].endswith("Same event.")
    assert f'"id": {target}' in user["content"]
    judge, seen = deepseek('{"title": " T ", "summary": "S"}')
    assert judge.rewrite([story], "Be brief.") == Draft("T", "S")
    assert "never copy a source's headline" in seen[0][1]["messages"][0]["content"]


@pytest.mark.parametrize(
    ("step", "content"),
    [
        ("relevant", "not json"),
        ("relevant", '{"relevant": "yes"}'),
        ("match", '{"match": "1"}'),
        ("rewrite", '{"summary": "no title"}'),
        ("rewrite", "[1]"),
    ],
)
def test_deepseek_rejects_broken_answers(conn, step, content):
    story = raw(conn, "https://a.example/feed", "Ankara'da sağanak yağış")
    judge, _ = deepseek(content)
    ask = {
        "relevant": lambda: judge.relevant(story, ""),
        "match": lambda: judge.match(story, [], ""),
        "rewrite": lambda: judge.rewrite([story], ""),
    }[step]
    with pytest.raises(ValueError):
        ask()


def checker(status, body):
    def handler(request):
        assert request.url.path == "/user/balance"
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(status, json=body)

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_check_key_reports_the_balance():
    body = {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "4.20"}]}
    result = check_key("sk-test", client_factory=checker(200, body))
    assert result == KeyCheck(True, "Key works with a balance of 4.20 USD.")


def test_check_key_with_an_empty_balance():
    body = {"is_available": False, "balance_infos": [{"currency": "USD", "total_balance": "0.00"}]}
    result = check_key("sk-test", client_factory=checker(200, body))
    assert not result.ok and "balance" in result.message


def test_check_key_rejected():
    assert check_key("sk-test", client_factory=checker(401, {})) == KeyCheck(
        False, "DeepSeek rejected this key."
    )


def test_check_key_offline():
    def broken():
        def handler(request):
            raise httpx.ConnectError("no network")

        return httpx.Client(transport=httpx.MockTransport(handler))

    result = check_key("sk-test", client_factory=broken)
    assert not result.ok and "Could not reach DeepSeek" in result.message


def ai_once(path, monkeypatch, process):
    """Runs run_ai for two polls with a fake pipeline."""
    stop = threading.Event()
    waits = []
    original_wait = stop.wait

    def wait(timeout=None):
        if waits:
            stop.set()
        waits.append(timeout)
        return original_wait(0)

    stop.wait = wait
    monkeypatch.setattr(loop, "process", process)
    loop.run_ai(path, stop, poll=0)


def test_ai_runs_only_with_a_key_and_when_started(conn, path, monkeypatch):
    calls = []

    def record(conn, judge, texts):
        calls.append(judge)

    db.settings.put(conn, "ai_running", "1")
    ai_once(path, monkeypatch, record)
    assert calls == []
    db.settings.put(conn, "deepseek_api_key", "sk-test")
    db.settings.put(conn, "ai_running", "")
    ai_once(path, monkeypatch, record)
    assert calls == []
    db.settings.put(conn, "ai_running", "1")
    ai_once(path, monkeypatch, record)
    assert len(calls) == 2 and calls[0].api_key == "sk-test"


def test_ai_works_while_the_fetcher_is_paused(conn, path, monkeypatch):
    db.settings.put(conn, "deepseek_api_key", "sk-test")
    db.settings.put(conn, "ai_running", "1")
    calls = []
    ai_once(path, monkeypatch, lambda conn, judge, texts: calls.append(texts))
    assert db.fetcher.get(conn).running is False and len(calls) == 2
    assert calls[0] == instructions.load(conn)


def test_ai_failure_is_recorded_and_waits_a_minute(conn, path, monkeypatch):
    db.settings.put(conn, "deepseek_api_key", "sk-test")
    db.settings.put(conn, "ai_running", "1")
    calls = []

    def broken(conn, judge, texts):
        calls.append(judge)
        raise RuntimeError("401 Unauthorized")

    ai_once(path, monkeypatch, broken)
    assert len(calls) == 1
    assert "401 Unauthorized" in db.settings.get(conn, "ai_status")
    ai_once(path, monkeypatch, lambda conn, judge, texts: 0)
    assert db.settings.get(conn, "ai_status") == "ok"


def test_the_language_setting_alone_decides_the_language():
    rewrite = next(step.default for step in instructions.STEPS if step.key == "rewrite")
    assert "language" not in rewrite.lower()
    assert instructions.in_language(rewrite, "").endswith("in the language of the sources.")
    assert instructions.in_language(rewrite, "Turkish").endswith(
        "in Turkish, whatever language the sources use."
    )


def local_server(status=200, body=None, content=None):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return (lambda: httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_local_judge_asks_the_local_server_and_reads_json_from_chatty_models(conn):
    story = raw(conn, "https://b.example/feed", "Ankara'da sağanak yağış")
    reply = '<think>Hmm, weather.</think>\n```json\n{"relevant": false, "reason": "Weather"}\n```'
    client, seen = local_server(content=reply)
    judge = local.LocalJudge("http://localhost:11434/v1", "llama3.1", client_factory=client)
    assert judge.relevant(story, "Only politics.") == Verdict(False, "Weather")
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "http://localhost:11434/v1/chat/completions"
    assert body["model"] == "llama3.1" and "response_format" not in body


@pytest.mark.parametrize(
    ("typed", "url"),
    [
        ("localhost:11434", "http://localhost:11434/v1"),
        ("http://localhost:1234/", "http://localhost:1234/v1"),
        ("http://192.168.1.5:1234/v1", "http://192.168.1.5:1234/v1"),
        ("  ", ""),
    ],
)
def test_local_addresses_are_normalized(typed, url):
    assert local.normalize(typed) == url


def test_checking_a_local_server_lists_its_models():
    client, _ = local_server(body={"data": [{"id": "qwen2.5"}, {"id": "llama3.1"}]})
    server = local.check_server("http://localhost:11434/v1", client_factory=client)
    assert server.ok and server.models == ("llama3.1", "qwen2.5")
    client, _ = local_server(body={"data": []})
    assert "no models" in local.check_server("http://x/v1", client_factory=client).message
    client, _ = local_server(status=404, body={})
    assert not local.check_server("http://x/v1", client_factory=client).ok

    def down():
        def refuse(request):
            raise httpx.ConnectError("refused")

        return httpx.Client(transport=httpx.MockTransport(refuse))

    server = local.check_server("http://localhost:1234/v1", client_factory=down)
    assert not server.ok and "Is Ollama or LM Studio running?" in server.message


def test_the_entry_in_use_decides_which_ai_writes(conn):
    assert state.judge(conn) is None
    state.add_key(conn, "sk-test1234")
    assert isinstance(state.judge(conn), DeepSeekJudge)
    state.add_local(conn, "http://localhost:11434/v1", "llama3.1")
    judge = state.judge(conn)
    assert isinstance(judge, local.LocalJudge) and judge.model == "llama3.1"
    assert state.key(conn) is None
    [entry] = [item for item in state.keys(conn) if item.local]
    assert (entry.name, entry.hint) == ("llama3.1", "localhost:11434")


def test_checking_a_model_says_which_ones_the_server_has():
    client, _ = local_server(body={"data": [{"id": "qwen2.5"}]})
    assert local.check_model("http://x/v1", "qwen2.5", client_factory=client).ok
    result = local.check_model("http://x/v1", "llama3.1", client_factory=client)
    assert result.message == "llama3.1 is not on that server. It has: qwen2.5."


def test_older_databases_get_the_new_key_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE api_keys (id INTEGER PRIMARY KEY, value TEXT NOT NULL UNIQUE,"
        " added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    old.execute("INSERT INTO api_keys (value) VALUES ('sk-old1234')")
    old.commit()
    old.close()
    conn = db.connect(path)
    [item] = state.keys(conn)
    assert item.kind == "deepseek" and item.model == "" and item.hint == "1234"
    conn.close()
