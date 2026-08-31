"""Runs a batch of synthetic (DiagnosisResult, expected explanations) examples
against a real LLMClient and reports schema-validity, factor-coverage, and
citation-safety rates — measured from the RAW model response (via
parse_explanations), before maica.reasoning.llm.explain_factors's fallback
logic would hide any of these failures.
"""

import json
from pathlib import Path

from maica.reasoning.llm import (
    _SYSTEM_PROMPT as SYSTEM_PROMPT,  # re-exported under a public name for callers
)
from maica.reasoning.llm import (
    LLMClient,
    LLMRequestError,
    factors_to_user_content,
    parse_explanations,
)
from maica.reasoning.models import DiagnosisResult, Factor
from pydantic import BaseModel, TypeAdapter, ValidationError


class EvalExample(BaseModel):
    diagnosis: DiagnosisResult
    meta: dict[str, object]


class BucketReport(BaseModel):
    n_examples: int
    schema_validity_rate: float
    factor_coverage_rate: float
    citation_safety_rate: float


class EvalReport(BaseModel):
    model: str
    n_examples: int
    schema_validity_rate: float
    factor_coverage_rate: float
    citation_safety_rate: float
    by_num_factors: dict[str, BucketReport]


def load_eval_examples(path: Path) -> list[EvalExample]:
    factors_adapter = TypeAdapter(list[dict])
    examples: list[EvalExample] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            raw_factors = factors_adapter.validate_json(row["user"])
            factors = [
                Factor(
                    label=item["label"],
                    rank=item["factor_rank"],
                    summary=item["summary"],
                    supporting_source_ids=item["supporting_source_ids"],
                )
                for item in raw_factors
            ]
            # target_source_id is unused by the harness (only .factors matters
            # downstream); a placeholder is fine here.
            diagnosis = DiagnosisResult(target_source_id="1001", factors=factors, gaps=[])
            examples.append(EvalExample(diagnosis=diagnosis, meta=row["meta"]))
    return examples


def _bucket_for(num_factors: int) -> str:
    if num_factors == 1:
        return "1"
    if num_factors == 2:
        return "2"
    if num_factors <= 4:
        return "3-4"
    if num_factors <= 6:
        return "5-6"
    return "7+"


class _RawResult(BaseModel):
    schema_valid: bool
    full_coverage: bool
    citation_safe: bool


async def _evaluate_one(example: EvalExample, *, client: LLMClient, model: str) -> _RawResult:
    factors = example.diagnosis.factors
    user_content = factors_to_user_content(factors)

    try:
        raw_text = await client.complete(model=model, system=SYSTEM_PROMPT, user=user_content)
        explanations = parse_explanations(raw_text)
    except (json.JSONDecodeError, ValidationError, TypeError, LLMRequestError):
        return _RawResult(schema_valid=False, full_coverage=False, citation_safe=False)

    explanation_by_rank = {e.factor_rank: e for e in explanations}
    full_coverage = all(f.rank in explanation_by_rank for f in factors)
    citation_safe = all(
        set(explanation_by_rank[f.rank].cited_source_ids).issubset(set(f.supporting_source_ids))
        for f in factors
        if f.rank in explanation_by_rank
    )
    return _RawResult(schema_valid=True, full_coverage=full_coverage, citation_safe=citation_safe)


def _rate(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def _summarize(results: list[_RawResult]) -> BucketReport:
    return BucketReport(
        n_examples=len(results),
        schema_validity_rate=_rate([r.schema_valid for r in results]),
        factor_coverage_rate=_rate([r.full_coverage for r in results]),
        citation_safety_rate=_rate([r.citation_safe for r in results]),
    )


async def run_eval(examples: list[EvalExample], *, client: LLMClient, model: str) -> EvalReport:
    results: list[_RawResult] = []
    buckets: dict[str, list[_RawResult]] = {}

    for example in examples:
        result = await _evaluate_one(example, client=client, model=model)
        results.append(result)
        bucket = _bucket_for(len(example.diagnosis.factors))
        buckets.setdefault(bucket, []).append(result)

    overall = _summarize(results)
    return EvalReport(
        model=model,
        n_examples=overall.n_examples,
        schema_validity_rate=overall.schema_validity_rate,
        factor_coverage_rate=overall.factor_coverage_rate,
        citation_safety_rate=overall.citation_safety_rate,
        by_num_factors={bucket: _summarize(rs) for bucket, rs in sorted(buckets.items())},
    )
