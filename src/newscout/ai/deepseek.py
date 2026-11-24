from collections.abc import Callable

import httpx

from newscout.ai.chat import ChatJudge, Check

URL = "https://api.deepseek.com"


class DeepSeekJudge(ChatJudge):
    name = "DeepSeek"
    json_mode = True

    def __init__(
        self,
        api_key: str,
        client_factory: Callable[[], httpx.Client] | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(URL, "deepseek-chat", api_key, client_factory, timeout)


def check_key(api_key: str, client_factory: Callable[[], httpx.Client] | None = None) -> Check:
    factory = client_factory or (lambda: httpx.Client(timeout=10))
    try:
        with factory() as client:
            response = client.get(
                f"{URL}/user/balance",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as error:
        return Check(False, f"Could not reach DeepSeek: {error}.")
    if response.status_code == 401:
        return Check(False, "DeepSeek rejected this key.")
    if response.is_error:
        return Check(False, f"DeepSeek answered {response.status_code}.")
    data = response.json()
    balance = next(iter(data.get("balance_infos") or []), {})
    amount = f"{balance.get('total_balance', '?')} {balance.get('currency', '')}".strip()
    if not data.get("is_available"):
        return Check(False, f"Key works but the balance is empty ({amount}).")
    return Check(True, f"Key works with a balance of {amount}.")
