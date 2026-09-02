import json

from maica.reasoning.chat import (
    ChatMessage,
    answer_question,
    build_evidence_context,
    prioritise_source_ids,
)
from maica.reasoning.llm import LLMRequestError, LLMTimeoutError
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


class _TimingOutClient:
    async def complete(self, *, model: str, system: str, user: str, json_mode: bool = True) -> str:
        raise LLMTimeoutError("took too long")


async def test_chat_tells_a_slow_model_apart_from_a_stopped_one() -> None:
    # Both are unavailability, but only one is worth waiting out — the report
    # page narrates each factor in its own call, and a local model serves them
    # one at a time, so a question asked mid-render queues behind them.
    timed_out = await answer_question(
        "anything", evidence_context="{}", history=[], client=_TimingOutClient(), model=_MODEL
    )
    unreachable = await answer_question(
        "anything", evidence_context="{}", history=[], client=_RaisingClient(), model=_MODEL
    )

    assert timed_out.grounded is False
    assert "took too long" in timed_out.answer
    assert unreachable.grounded is False
    assert "could not be reached" in unreachable.answer


def _big_diagnosis(source_id: str) -> DiagnosisResult:
    return DiagnosisResult(
        target_source_id=source_id,
        factors=[
            Factor(
                label=FactorLabel.UNCERTAIN,
                rank=rank,
                summary="x" * 400,
                supporting_source_ids=[f"{n}" for n in range(40)],
            )
            for rank in range(1, 9)
        ],
        gaps=[Gap(description="d" * 200, reason="r" * 200)],
    )


def test_evidence_bundle_stays_inside_a_model_context_window() -> None:
    # A 5,000-record account produced a 900,000-character bundle — roughly
    # 225k tokens against a 41k window, so it overflowed silently and the model
    # answered from whatever fragment survived.
    diagnoses = [_big_diagnosis(str(i)) for i in range(500)]

    context = build_evidence_context([], diagnoses, records_in_analysis=5000)

    assert len(context) <= 45_000
    assert len(json.loads(context)["analysed_records"]) < len(diagnoses)


def test_bundle_declares_that_it_covers_only_part_of_the_analysis() -> None:
    diagnoses = [_big_diagnosis(str(i)) for i in range(500)]

    coverage = json.loads(build_evidence_context([], diagnoses, records_in_analysis=5000))[
        "coverage"
    ]

    assert coverage["is_partial"] is True
    assert coverage["records_in_this_analysis"] == 5000
    assert coverage["records_analysed_in_this_bundle"] < 500


def test_a_bundle_covering_everything_does_not_claim_to_be_partial() -> None:
    coverage = json.loads(build_evidence_context([], [_diagnosis()], records_in_analysis=1))[
        "coverage"
    ]

    assert coverage["is_partial"] is False


def test_at_least_one_record_survives_even_when_it_blows_the_budget() -> None:
    # Trimming must never produce an empty bundle — the record in focus is the
    # whole point of the question.
    huge = DiagnosisResult(
        target_source_id="1001",
        factors=[
            Factor(
                label=FactorLabel.UNCERTAIN, rank=1, summary="y" * 200_000, supporting_source_ids=[]
            )
        ],
        gaps=[],
    )

    analysed = json.loads(build_evidence_context([], [huge], records_in_analysis=1))[
        "analysed_records"
    ]

    assert len(analysed) == 1


def test_prioritise_puts_the_record_on_screen_first_then_its_relations() -> None:
    ordered = prioritise_source_ids(
        ["1001", "1002", "1003", "1004"], focus_source_id="1004", related_source_ids=["1002"]
    )

    assert ordered[:2] == ["1004", "1002"]
    assert sorted(ordered) == ["1001", "1002", "1003", "1004"]


def test_prioritise_ignores_a_focus_record_not_in_this_analysis() -> None:
    ordered = prioritise_source_ids(["1001", "1002"], focus_source_id="9999", related_source_ids=[])

    assert ordered == ["1001", "1002"]
