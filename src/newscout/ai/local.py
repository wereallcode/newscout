"""A model running on your own machine, served by Ollama or LM Studio.

Both speak the same chat API as DeepSeek, so the local judge only changes where
it asks and which model answers.
"""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from newscout.ai.deepseek import DeepSeekJudge, KeyCheck

# Where each app listens by default, and a small current model each can run on most computers,
# written the way that app names it.
SERVERS = {"Ollama": "http://localhost:11434/v1", "LM Studio": "http://localhost:1234/v1"}
SUGGESTED = {"Ollama": "qwen3:4b", "LM Studio": "qwen/qwen3-4b"}


class LocalJudge(DeepSeekJudge):
    name = "the local model"
    json_mode = False

    def __init__(
        self,
        base_url: str,
        model: str,
        client_factory: Callable[[], httpx.Client] | None = None,
        timeout: float = 120.0,
    ) -> None:
        # Local servers ignore the key; a model on a laptop needs longer than an API.
        super().__init__("local", client_factory, timeout)
        self.base_url = base_url
        self.model = model


def normalize(url: str) -> str:
    """Accepts 'localhost:11434' or a full address and returns the API base with /v1."""
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    if url and not urlparse(url).path.endswith("/v1"):
        url += "/v1"
    return url


@dataclass(frozen=True)
class Server:
    ok: bool
    message: str
    models: tuple[str, ...] = ()


# Listing the models proves the server is up and shows what it can run.
def check_server(base_url: str, client_factory: Callable[[], httpx.Client] | None = None) -> Server:
    factory = client_factory or (lambda: httpx.Client(timeout=3))
    try:
        with factory() as client:
            response = client.get(f"{base_url}/models")
    except httpx.HTTPError:
        return Server(False, f"Nothing answered at {base_url}. Is Ollama or LM Studio running?")
    if response.is_error:
        return Server(False, f"The server at {base_url} answered {response.status_code}.")
    try:
        models = tuple(sorted(item["id"] for item in response.json()["data"]))
    except (KeyError, TypeError, ValueError):
        return Server(False, f"The server at {base_url} is not an Ollama or LM Studio API.")
    if not models:
        return Server(False, "The server is running but has no models. Download one first.")
    return Server(
        True, f"Connected, {len(models)} {'model' if len(models) == 1 else 'models'}.", models
    )


def check_model(
    base_url: str, model: str, client_factory: Callable[[], httpx.Client] | None = None
) -> KeyCheck:
    server = check_server(base_url, client_factory)
    if not server.ok:
        return KeyCheck(False, server.message)
    if model not in server.models:
        return KeyCheck(
            False, f"{model} is not on that server. It has: {', '.join(server.models)}."
        )
    return KeyCheck(True, f"{model} is ready.")
