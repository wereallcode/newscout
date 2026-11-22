import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from newscout.ai.pipeline import Draft, Verdict
from newscout.models import Event, Story

URL = "https://api.deepseek.com"

RELEVANCE = """You decide whether a raw news story belongs in the user's news list.
Answer with JSON only: {"relevant": true | false, "reason": "..."}
"reason" is a few words explaining a false. Follow these instructions from the user:
"""

MERGE = """You decide whether a raw news story reports the same real-world event as one of the
candidate news items. Answer with JSON only: {"match": <candidate id or null>}
Follow these instructions from the user:
"""

REWRITE = """You write one news item from one or more source stories about the same event.
Always write "title" and "summary" in your own words; never copy a source's headline.
Answer with JSON only: {"title": "...", "summary": "..."}
Follow these instructions from the user:
"""


def _story(story: Story) -> dict[str, str]:
    return {"title": story.title, "summary": story.summary, "source": story.source_name}


class DeepSeekJudge:
    def __init__(
        self,
        api_key: str,
        client_factory: Callable[[], httpx.Client] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.client_factory = client_factory or (lambda: httpx.Client(timeout=timeout))

    def relevant(self, story: Story, instructions: str) -> Verdict:
        answer = self._ask(RELEVANCE + instructions, _story(story))
        if not isinstance(answer.get("relevant"), bool):
            raise ValueError(f"Unexpected answer from DeepSeek: {answer}")
        return Verdict(answer["relevant"], answer.get("reason") or None)

    def match(self, story: Story, candidates: list[Event], instructions: str) -> int | None:
        options = [{"id": c.id, "title": c.title, "summary": c.summary} for c in candidates]
        answer = self._ask(MERGE + instructions, {"raw": _story(story), "candidates": options})
        match = answer.get("match")
        if match is not None and not isinstance(match, int):
            raise ValueError(f"Unexpected answer from DeepSeek: {answer}")
        return match

    def rewrite(self, stories: list[Story], instructions: str) -> Draft:
        answer = self._ask(REWRITE + instructions, {"sources": [_story(s) for s in stories]})
        title, summary = answer.get("title"), answer.get("summary")
        if not isinstance(title, str) or not title.strip() or not isinstance(summary, str):
            raise ValueError(f"Unexpected answer from DeepSeek: {answer}")
        return Draft(title.strip(), summary.strip())

    def _ask(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.client_factory() as client:
            response = client.post(
                f"{URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "deepseek-chat",
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
        try:
            answer = json.loads(response.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"Unexpected answer from DeepSeek: {error}") from error
        if not isinstance(answer, dict):
            raise ValueError(f"Unexpected answer from DeepSeek: {answer}")
        return answer


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    message: str


# The balance endpoint proves the key works without spending tokens.
def check_key(api_key: str, client_factory: Callable[[], httpx.Client] | None = None) -> KeyCheck:
    factory = client_factory or (lambda: httpx.Client(timeout=10))
    try:
        with factory() as client:
            response = client.get(
                f"{URL}/user/balance",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as error:
        return KeyCheck(False, f"Could not reach DeepSeek: {error}.")
    if response.status_code == 401:
        return KeyCheck(False, "DeepSeek rejected this key.")
    if response.is_error:
        return KeyCheck(False, f"DeepSeek answered {response.status_code}.")
    data = response.json()
    balance = next(iter(data.get("balance_infos") or []), {})
    amount = f"{balance.get('total_balance', '?')} {balance.get('currency', '')}".strip()
    if not data.get("is_available"):
        return KeyCheck(False, f"Key works but the balance is empty ({amount}).")
    return KeyCheck(True, f"Key works with a balance of {amount}.")
