import httpx

from maica.reasoning.llm import LLMRequestError


class OllamaClient:
    """Talks to a local Ollama server's /api/chat endpoint. Implements the
    LLMClient protocol structurally — no shared base class needed."""

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def complete(self, *, model: str, system: str, user: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http_client:
                response = await http_client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "stream": False,
                        "format": "json",
                        "think": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return str(data["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMRequestError(f"Ollama request failed: {exc}") from exc
