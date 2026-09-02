import httpx

from maica.reasoning.llm import LLMRequestError, LLMTimeoutError


class OllamaClient:
    """Talks to a local Ollama server's /api/chat endpoint. Implements the
    LLMClient protocol structurally — no shared base class needed."""

    def __init__(self, base_url: str, timeout: float = 180.0, context_tokens: int = 16384) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._context_tokens = context_tokens

    async def complete(self, *, model: str, system: str, user: str, json_mode: bool = True) -> str:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            # Ollama's default context window is a few thousand tokens whatever
            # the model supports, and it truncates silently past that. Set it
            # explicitly or a long evidence bundle is quietly cut in half.
            "options": {"num_ctx": self._context_tokens},
        }
        if json_mode:
            # Constrains the model to emit valid JSON. Right for the narrator,
            # wrong for prose answers — without the switch, chat replies come
            # back as raw JSON objects instead of sentences.
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http_client:
                response = await http_client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["message"]["content"])
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Ollama did not answer within {self._timeout:.0f}s: {exc}"
            ) from exc
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMRequestError(f"Ollama request failed: {exc}") from exc
