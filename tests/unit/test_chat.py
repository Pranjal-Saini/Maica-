import json

from maica.reasoning.chat import ChatMessage, answer_question, build_evidence_context
from maica.reasoning.llm import LLMRequestError
from maica.reasoning.models import DiagnosisResult, Factor, FactorLabel, Gap

_MODEL = "qwen3:8b"


class _RecordingClient:
    def __init__(self, response: str = "A plain sentence answer.") -> None:
        self._response = response
        self.last_kwargs: dict = {}

    async def complete(self, *, model: str, system: str, user: str, json_mode: bool = True) -> str:
        self.last_kwargs = {
            "model": model,
            "system": system,
            "user": user,
            "json_mode": json_mode,
        }
        return self._response


class _RaisingClient:
    async def complete(self, *, model: str, system: str, user: str, json_mode: bool = True) -> str:
        raise LLMRequestError("ollama down")


def _diagnosis() -> DiagnosisResult:
    return DiagnosisResult(
        target_source_id="1001",
        factors=[
            Factor(
                label=FactorLabel.UNCERTAIN,
                rank=1,
                summary="amount changed from '1500.00' to '1800.00'",
                supporting_source_ids=["1001"],
            )
        ],
        gaps=[Gap(description="no script evidence", reason="none ingested")],
    )


async def test_chat_asks_for_prose_not_json() -> None:
    # Regression: OllamaClient defaults to JSON mode for the narrator. Chat
    # answers are prose for a human, so it must opt out — otherwise replies
    # come back as raw JSON objects instead of sentences.
    client = _RecordingClient()

    await answer_question(
        "what changed?",
        evidence_context="{}",
        history=[],
        client=client,
        model=_MODEL,
    )

    assert client.last_kwargs["json_mode"] is False


async def test_chat_sends_only_this_analysis_evidence() -> None:
    client = _RecordingClient()
    context = build_evidence_context([], [_diagnosis()])

    await answer_question(
        "what changed?", evidence_context=context, history=[], client=client, model=_MODEL
    )

    sent = client.last_kwargs["user"]
    assert "1500.00" in sent
    assert "no script evidence" in sent
    assert "what changed?" in sent


async def test_chat_includes_recent_history() -> None:
    client = _RecordingClient()
    history = [
        ChatMessage(role="user", content="earlier question"),
        ChatMessage(role="assistant", content="earlier answer"),
    ]

    await answer_question(
        "follow up", evidence_context="{}", history=history, client=client, model=_MODEL
    )

    sent = client.last_kwargs["user"]
    assert "earlier question" in sent
    assert "earlier answer" in sent


async def test_chat_without_client_returns_honest_message() -> None:
    result = await answer_question(
        "anything", evidence_context="{}", history=[], client=None, model=_MODEL
    )

    assert result.grounded is False
    assert "not available" in result.answer


async def test_chat_survives_model_failure() -> None:
    result = await answer_question(
        "anything", evidence_context="{}", history=[], client=_RaisingClient(), model=_MODEL
    )

    assert result.grounded is False
    assert "could not be reached" in result.answer


def test_evidence_context_carries_factors_and_gaps() -> None:
    context = json.loads(build_evidence_context([], [_diagnosis()]))

    analysed = context["analysed_records"][0]
    assert analysed["source_id"] == "1001"
    assert analysed["ranked_factors"][0]["label"] == "UNCERTAIN"
    assert analysed["gaps"][0]["description"] == "no script evidence"
