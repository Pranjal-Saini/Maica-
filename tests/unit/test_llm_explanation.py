import json

from maica.reasoning.llm import LLMRequestError, explain_factors
from maica.reasoning.models import DiagnosisResult, Factor, FactorLabel, Gap

_MODEL = "qwen3:8b"


def _diagnosis_with_one_factor() -> DiagnosisResult:
    factor = Factor(
        label=FactorLabel.UNCERTAIN,
        rank=1,
        summary="Shares account = '4000 - Revenue' with 1 other record(s): 1003.",
        supporting_source_ids=["1001", "1003"],
    )
    return DiagnosisResult(target_source_id="1001", factors=[factor], gaps=[])


def _diagnosis_with_n_factors(n: int) -> DiagnosisResult:
    factors = [
        Factor(
            label=FactorLabel.UNCERTAIN,
            rank=i,
            summary=f"summary {i}",
            supporting_source_ids=["1001", f"200{i}"],
        )
        for i in range(1, n + 1)
    ]
    return DiagnosisResult(target_source_id="1001", factors=factors, gaps=[])


class _FakeClient:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def complete(self, *, model: str, system: str, user: str) -> str:
        return self._response_text


class _RaisingClient:
    async def complete(self, *, model: str, system: str, user: str) -> str:
        raise LLMRequestError("network exploded")


class _ScriptedClient:
    """Returns one pre-scripted response per call, in order — lets a test
    make factor 2's call fail while factor 1's and 3's succeed."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def complete(self, *, model: str, system: str, user: str) -> str:
        self.calls.append(user)
        response = self._responses[len(self.calls) - 1]
        return response


async def test_no_client_falls_back_to_rule_based_summary() -> None:
    diagnosis = _diagnosis_with_one_factor()

    result = await explain_factors(diagnosis, client=None, model=_MODEL)

    assert len(result.explained_factors) == 1
    assert result.explained_factors[0].explanation_source == "fallback"
    assert result.explained_factors[0].explanation == diagnosis.factors[0].summary
    assert any("not generated" in g.description for g in result.gaps)


async def test_valid_llm_response_is_used_verbatim() -> None:
    diagnosis = _diagnosis_with_one_factor()
    response_text = json.dumps(
        [
            {
                "factor_rank": 1,
                "explanation": "Both transactions post to Revenue — worth checking together.",
                "cited_source_ids": ["1001", "1003"],
            }
        ]
    )
    client = _FakeClient(response_text)

    result = await explain_factors(diagnosis, client=client, model=_MODEL)

    assert result.explained_factors[0].explanation_source == "llm"
    assert "worth checking together" in result.explained_factors[0].explanation
    assert not any("fell back" in g.description for g in result.gaps)


async def test_bare_object_response_is_repaired_into_a_single_element_array() -> None:
    diagnosis = _diagnosis_with_one_factor()
    # Some models return a bare object instead of a 1-element array when
    # there's only one factor — this should be repaired, not rejected.
    response_text = json.dumps(
        {
            "factor_rank": 1,
            "explanation": "Repaired from a bare object.",
            "cited_source_ids": ["1001", "1003"],
        }
    )
    client = _FakeClient(response_text)

    result = await explain_factors(diagnosis, client=client, model=_MODEL)

    assert result.explained_factors[0].explanation_source == "llm"
    assert result.explained_factors[0].explanation == "Repaired from a bare object."


async def test_llm_response_citing_unknown_source_id_falls_back() -> None:
    diagnosis = _diagnosis_with_one_factor()
    response_text = json.dumps(
        [
            {
                "factor_rank": 1,
                "explanation": "This references a record never given to it.",
                "cited_source_ids": ["9999"],
            }
        ]
    )
    client = _FakeClient(response_text)

    result = await explain_factors(diagnosis, client=client, model=_MODEL)

    assert result.explained_factors[0].explanation_source == "fallback"
    assert any("fell back" in g.description for g in result.gaps)


async def test_malformed_json_falls_back() -> None:
    diagnosis = _diagnosis_with_one_factor()
    client = _FakeClient("not json at all")

    result = await explain_factors(diagnosis, client=client, model=_MODEL)

    assert result.explained_factors[0].explanation_source == "fallback"
    assert any("fell back" in g.description for g in result.gaps)


async def test_request_failure_falls_back() -> None:
    diagnosis = _diagnosis_with_one_factor()

    result = await explain_factors(diagnosis, client=_RaisingClient(), model=_MODEL)

    assert result.explained_factors[0].explanation_source == "fallback"


async def test_multi_factor_diagnosis_makes_one_call_per_factor() -> None:
    diagnosis = _diagnosis_with_n_factors(3)
    responses = [
        json.dumps([{"factor_rank": i, "explanation": f"e{i}", "cited_source_ids": ["1001"]}])
        for i in range(1, 4)
    ]
    client = _ScriptedClient(responses)

    result = await explain_factors(diagnosis, client=client, model=_MODEL)

    assert len(client.calls) == 3
    assert all(ef.explanation_source == "llm" for ef in result.explained_factors)
    assert [ef.explanation for ef in result.explained_factors] == ["e1", "e2", "e3"]


async def test_one_bad_factor_call_does_not_affect_the_others() -> None:
    # This is the whole point of calling per-factor instead of batching: a
    # single bad response only costs that one factor, not the entire batch.
    diagnosis = _diagnosis_with_n_factors(3)
    responses = [
        json.dumps([{"factor_rank": 1, "explanation": "e1", "cited_source_ids": ["1001"]}]),
        "not json at all — this call fails",
        json.dumps([{"factor_rank": 3, "explanation": "e3", "cited_source_ids": ["1001"]}]),
    ]
    client = _ScriptedClient(responses)

    result = await explain_factors(diagnosis, client=client, model=_MODEL)

    assert len(client.calls) == 3
    sources = [ef.explanation_source for ef in result.explained_factors]
    assert sources == ["llm", "fallback", "llm"]
    assert result.explained_factors[1].explanation == diagnosis.factors[1].summary
    assert any("fell back" in g.description for g in result.gaps)


async def test_no_factors_short_circuits_without_touching_client() -> None:
    diagnosis = DiagnosisResult(
        target_source_id="1001",
        factors=[],
        gaps=[Gap(description="no factors", reason="none found")],
    )

    result = await explain_factors(diagnosis, client=_RaisingClient(), model="whatever")

    assert result.explained_factors == []
    assert result.gaps == diagnosis.gaps
