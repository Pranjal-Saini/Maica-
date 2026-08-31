import json
from types import SimpleNamespace

from anthropic import AnthropicError

from maica.reasoning.llm import explain_factors
from maica.reasoning.models import DiagnosisResult, Factor, FactorLabel, Gap


def _diagnosis_with_one_factor() -> DiagnosisResult:
    factor = Factor(
        label=FactorLabel.UNCERTAIN,
        rank=1,
        summary="Shares account = '4000 - Revenue' with 1 other record(s): 1003.",
        supporting_source_ids=["1001", "1003"],
    )
    return DiagnosisResult(target_source_id="1001", factors=[factor], gaps=[])


class _FakeMessages:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def create(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(content=[SimpleNamespace(text=self._response_text)])


class _FakeClient:
    def __init__(self, response_text: str) -> None:
        self.messages = _FakeMessages(response_text)


class _RaisingMessages:
    async def create(self, **_kwargs: object) -> SimpleNamespace:
        raise AnthropicError("network exploded")


class _RaisingClient:
    def __init__(self) -> None:
        self.messages = _RaisingMessages()


async def test_no_client_falls_back_to_rule_based_summary() -> None:
    diagnosis = _diagnosis_with_one_factor()

    result = await explain_factors(diagnosis, client=None, model="claude-haiku-4-5-20251001")

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

    result = await explain_factors(diagnosis, client=client, model="claude-haiku-4-5-20251001")

    assert result.explained_factors[0].explanation_source == "llm"
    assert "worth checking together" in result.explained_factors[0].explanation
    assert not any("fell back" in g.description for g in result.gaps)


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

    result = await explain_factors(diagnosis, client=client, model="claude-haiku-4-5-20251001")

    assert result.explained_factors[0].explanation_source == "fallback"
    assert any("fell back" in g.description for g in result.gaps)


async def test_malformed_json_falls_back() -> None:
    diagnosis = _diagnosis_with_one_factor()
    client = _FakeClient("not json at all")

    result = await explain_factors(diagnosis, client=client, model="claude-haiku-4-5-20251001")

    assert result.explained_factors[0].explanation_source == "fallback"
    assert any("could not be generated" in g.description for g in result.gaps)


async def test_api_failure_falls_back() -> None:
    diagnosis = _diagnosis_with_one_factor()

    result = await explain_factors(
        diagnosis, client=_RaisingClient(), model="claude-haiku-4-5-20251001"
    )

    assert result.explained_factors[0].explanation_source == "fallback"


async def test_no_factors_short_circuits_without_touching_client() -> None:
    diagnosis = DiagnosisResult(
        target_source_id="1001",
        factors=[],
        gaps=[Gap(description="no factors", reason="none found")],
    )

    result = await explain_factors(diagnosis, client=_RaisingClient(), model="whatever")

    assert result.explained_factors == []
    assert result.gaps == diagnosis.gaps
