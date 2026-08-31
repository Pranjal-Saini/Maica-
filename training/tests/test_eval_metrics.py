import json

from maica.reasoning.models import DiagnosisResult, Factor, FactorLabel

from eval.harness import EvalExample, _bucket_for, run_eval


def _example(factors: list[Factor]) -> EvalExample:
    diagnosis = DiagnosisResult(target_source_id="1001", factors=factors, gaps=[])
    return EvalExample(diagnosis=diagnosis, meta={"num_factors": len(factors)})


def _factor(rank: int, supporting: list[str]) -> Factor:
    return Factor(
        label=FactorLabel.UNCERTAIN,
        rank=rank,
        summary=f"summary {rank}",
        supporting_source_ids=supporting,
    )


class _ScriptedClient:
    """Returns pre-scripted responses in call order, for deterministic tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete(self, *, model: str, system: str, user: str) -> str:
        response = self._responses[self.calls]
        self.calls += 1
        return response


def test_bucket_assignment() -> None:
    assert _bucket_for(1) == "1"
    assert _bucket_for(2) == "2"
    assert _bucket_for(3) == "3-4"
    assert _bucket_for(4) == "3-4"
    assert _bucket_for(5) == "5-6"
    assert _bucket_for(6) == "5-6"
    assert _bucket_for(7) == "7+"
    assert _bucket_for(20) == "7+"


async def test_run_eval_perfect_responses_scores_100_percent() -> None:
    example = _example([_factor(1, ["1001", "1002"]), _factor(2, ["1001", "1003"])])
    response = json.dumps(
        [
            {"factor_rank": 1, "explanation": "e1", "cited_source_ids": ["1001", "1002"]},
            {"factor_rank": 2, "explanation": "e2", "cited_source_ids": ["1001"]},
        ]
    )
    client = _ScriptedClient([response])

    report = await run_eval([example], client=client, model="test-model")

    assert report.schema_validity_rate == 1.0
    assert report.factor_coverage_rate == 1.0
    assert report.citation_safety_rate == 1.0
    assert report.by_num_factors["2"].n_examples == 1


async def test_run_eval_malformed_json_scores_zero() -> None:
    example = _example([_factor(1, ["1001"])])
    client = _ScriptedClient(["not json"])

    report = await run_eval([example], client=client, model="test-model")

    assert report.schema_validity_rate == 0.0
    assert report.factor_coverage_rate == 0.0
    assert report.citation_safety_rate == 0.0


async def test_run_eval_dropped_factor_fails_coverage_but_not_schema() -> None:
    example = _example([_factor(1, ["1001"]), _factor(2, ["1001"])])
    # valid JSON, but only covers factor_rank 1 — factor 2 was dropped
    response = json.dumps([{"factor_rank": 1, "explanation": "e1", "cited_source_ids": ["1001"]}])
    client = _ScriptedClient([response])

    report = await run_eval([example], client=client, model="test-model")

    assert report.schema_validity_rate == 1.0
    assert report.factor_coverage_rate == 0.0


async def test_run_eval_invented_citation_fails_citation_safety_only() -> None:
    example = _example([_factor(1, ["1001"])])
    response = json.dumps([{"factor_rank": 1, "explanation": "e1", "cited_source_ids": ["9999"]}])
    client = _ScriptedClient([response])

    report = await run_eval([example], client=client, model="test-model")

    assert report.schema_validity_rate == 1.0
    assert report.factor_coverage_rate == 1.0
    assert report.citation_safety_rate == 0.0


async def test_run_eval_bare_object_is_repaired_not_penalized() -> None:
    example = _example([_factor(1, ["1001"])])
    response = json.dumps({"factor_rank": 1, "explanation": "e1", "cited_source_ids": ["1001"]})
    client = _ScriptedClient([response])

    report = await run_eval([example], client=client, model="test-model")

    assert report.schema_validity_rate == 1.0
    assert report.factor_coverage_rate == 1.0
