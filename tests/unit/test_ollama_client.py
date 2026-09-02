import httpx
import pytest
import respx

from maica.reasoning.llm import LLMRequestError, LLMTimeoutError
from maica.reasoning.ollama_client import OllamaClient


@respx.mock
async def test_complete_returns_message_content() -> None:
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(
            200, json={"message": {"role": "assistant", "content": '[{"factor_rank": 1}]'}}
        )
    )
    client = OllamaClient(base_url="http://localhost:11434")

    result = await client.complete(model="qwen3:8b", system="sys", user="usr")

    assert result == '[{"factor_rank": 1}]'


@respx.mock
async def test_complete_sends_expected_payload() -> None:
    route = respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "ok"}})
    )
    client = OllamaClient(base_url="http://localhost:11434")

    await client.complete(model="qwen3:8b", system="the system prompt", user="the user content")

    sent = route.calls.last.request
    body = httpx.Response(200, content=sent.content).json()
    assert body["model"] == "qwen3:8b"
    assert body["messages"][0] == {"role": "system", "content": "the system prompt"}
    assert body["messages"][1] == {"role": "user", "content": "the user content"}
    assert body["think"] is False
    assert body["stream"] is False


@respx.mock
async def test_non_2xx_response_raises_llm_request_error() -> None:
    respx.post("http://localhost:11434/api/chat").mock(return_value=httpx.Response(500))
    client = OllamaClient(base_url="http://localhost:11434")

    try:
        await client.complete(model="qwen3:8b", system="sys", user="usr")
        raised = False
    except LLMRequestError:
        raised = True
    assert raised


@respx.mock
async def test_connection_error_raises_llm_request_error() -> None:
    respx.post("http://localhost:11434/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    client = OllamaClient(base_url="http://localhost:11434")

    try:
        await client.complete(model="qwen3:8b", system="sys", user="usr")
        raised = False
    except LLMRequestError:
        raised = True
    assert raised


@respx.mock
async def test_missing_message_field_raises_llm_request_error() -> None:
    respx.post("http://localhost:11434/api/chat").mock(return_value=httpx.Response(200, json={}))
    client = OllamaClient(base_url="http://localhost:11434")

    try:
        await client.complete(model="qwen3:8b", system="sys", user="usr")
        raised = False
    except LLMRequestError:
        raised = True
    assert raised


@respx.mock
async def test_timeout_raises_a_distinguishable_error() -> None:
    # A slow local model and a stopped one need different advice, so the
    # timeout must not collapse into the generic request failure.
    respx.post("http://localhost:11434/api/chat").mock(side_effect=httpx.ReadTimeout("timed out"))
    client = OllamaClient(base_url="http://localhost:11434", timeout=1.0)

    with pytest.raises(LLMTimeoutError):
        await client.complete(model="qwen3:8b", system="sys", user="usr")


@respx.mock
async def test_connection_failure_is_not_reported_as_a_timeout() -> None:
    respx.post("http://localhost:11434/api/chat").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    client = OllamaClient(base_url="http://localhost:11434")

    with pytest.raises(LLMRequestError) as exc_info:
        await client.complete(model="qwen3:8b", system="sys", user="usr")
    assert not isinstance(exc_info.value, LLMTimeoutError)
