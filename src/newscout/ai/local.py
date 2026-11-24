from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from newscout.ai.chat import ChatJudge, Check

SERVERS = {"Ollama": "http://localhost:11434/v1", "LM Studio": "http://localhost:1234/v1"}
SUGGESTED = {"Ollama": "qwen3:4b", "LM Studio": "qwen/qwen3-4b"}


class LocalJudge(ChatJudge):
    name = "the local model"
    json_mode = False

    def __init__(
        self,
        base_url: str,
        model: str,
        client_factory: Callable[[], httpx.Client] | None = None,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(base_url, model, "", client_factory, timeout)


def normalize(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    if url and not urlparse(url).path.endswith("/v1"):
        url += "/v1"
    return url


class Unreachable(Exception):
    pass


def models(base_url: str, client_factory: Callable[[], httpx.Client] | None = None) -> list[str]:
    factory = client_factory or (lambda: httpx.Client(timeout=3))
    try:
        with factory() as client:
            response = client.get(f"{base_url}/models")
    except httpx.HTTPError as error:
        message = f"Nothing answered at {base_url}. Is Ollama or LM Studio running?"
        raise Unreachable(message) from error
    if response.is_error:
        raise Unreachable(f"The server at {base_url} answered {response.status_code}.")
    try:
        return sorted(item["id"] for item in response.json()["data"])
    except (KeyError, TypeError, ValueError) as error:
        message = f"The server at {base_url} is not an Ollama or LM Studio API."
        raise Unreachable(message) from error


def check_model(
    base_url: str, model: str, client_factory: Callable[[], httpx.Client] | None = None
) -> Check:
    try:
        available = models(base_url, client_factory)
    except Unreachable as error:
        return Check(False, str(error))
    if not available:
        return Check(False, "The server is running but has no models. Download one first.")
    if model not in available:
        return Check(False, f"{model} is not on that server. It has: {', '.join(available)}.")
    return Check(True, f"{model} is ready.")
