import json
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from maica.reasoning.models import DiagnosisResult, Factor, Gap

PROMPT_VERSION = "v1"

_SYSTEM_PROMPT = f"""You are explaining pre-computed contributing factors for a \
NetSuite transaction investigation, for a NetSuite consultant. You do not decide \
which factors matter or how confident to be — that ranking and label have already \
been computed deterministically and are given to you as input.

Your only job: turn each factor's terse summary and its cited record IDs into one \
or two clear, plain sentences a consultant can act on.

Rules you must follow exactly:
- Never invent evidence. Only reference record IDs given to you in the input.
- Never state or imply a stronger or weaker confidence than the label already \
given to you — you are explaining it, not re-judging it.
- Respond with strict JSON only, no prose before or after it, matching this shape.
  ALWAYS return a JSON array, even when there is only one factor — never a bare
  object:
  [{{"factor_rank": <int>, "explanation": "<string>", "cited_source_ids": ["<string>", ...]}}]

Prompt version: {PROMPT_VERSION}"""


class LLMRequestError(Exception):
    """Raised by an LLMClient implementation when the completion request
    itself fails (network error, non-2xx response, unreachable host, etc.) —
    distinct from a successful response that fails schema validation."""


class LLMClient(Protocol):
    """One interface any local or hosted model can implement, so this module
    never depends on a specific provider's SDK."""

    async def complete(self, *, model: str, system: str, user: str) -> str: ...


class FactorExplanation(BaseModel):
    factor_rank: int
    explanation: str
    cited_source_ids: list[str]


class ExplainedFactor(BaseModel):
    factor: Factor
    explanation: str
    explanation_source: Literal["llm", "fallback"]


class ExplainedDiagnosis(BaseModel):
    target_source_id: str
    explained_factors: list[ExplainedFactor]
    gaps: list[Gap]


def factors_to_user_content(factors: Sequence[Factor]) -> str:
    """The exact JSON shape sent to the model for one batch of factors — a
    single source of truth so training-data generation and the eval harness
    build requests identically to production, never a hand-copied variant."""
    return json.dumps(
        [
            {
                "factor_rank": f.rank,
                "label": f.label.value,
                "summary": f.summary,
                "supporting_source_ids": f.supporting_source_ids,
            }
            for f in factors
        ]
    )


def parse_explanations(raw_text: str) -> list[FactorExplanation]:
    """Parses and schema-validates one model response. Repairs a bare object
    into a single-element array (small models sometimes drop the array
    wrapper when there's only one factor) but otherwise raises
    json.JSONDecodeError / ValidationError / TypeError on malformed input —
    callers decide how to react. Split out from explain_factors so an eval
    harness can measure raw model output before fallback logic hides it."""
    parsed = json.loads(raw_text)
    if isinstance(parsed, dict):
        parsed = [parsed]
    return [FactorExplanation.model_validate(item) for item in parsed]


def _fallback(diagnosis: DiagnosisResult, extra_gap: Gap) -> ExplainedDiagnosis:
    return ExplainedDiagnosis(
        target_source_id=diagnosis.target_source_id,
        explained_factors=[
            ExplainedFactor(factor=f, explanation=f.summary, explanation_source="fallback")
            for f in diagnosis.factors
        ],
        gaps=[*diagnosis.gaps, extra_gap],
    )


async def _explain_one_factor(
    factor: Factor, *, client: LLMClient, model: str
) -> FactorExplanation | None:
    """One model call for exactly one factor. Returns None on any request or
    schema failure — the caller falls back to that single factor's
    deterministic summary rather than losing the whole batch to one bad call."""
    user_content = factors_to_user_content([factor])
    try:
        raw_text = await client.complete(model=model, system=_SYSTEM_PROMPT, user=user_content)
        explanations = parse_explanations(raw_text)
    except (json.JSONDecodeError, ValidationError, TypeError, LLMRequestError):
        return None
    return next((e for e in explanations if e.factor_rank == factor.rank), None)


async def explain_factors(
    diagnosis: DiagnosisResult,
    *,
    client: LLMClient | None,
    model: str,
) -> ExplainedDiagnosis:
    """Turns already-ranked, evidence-backed factors into consultant-facing
    prose. The LLM explains; it never re-ranks, invents a factor, or cites a
    record ID outside what that factor already cited (llm-rules.md,
    reasoning-rules.md: "the LLM explains evidence; it is not the source of
    truth"). A missing client, a request failure, or a schema/citation
    violation all fall back to the deterministic summary — the diagnosis is
    always usable even when the LLM step fails outright.

    Calls the model once per factor rather than once for the whole batch.
    Live testing showed a single-factor call is reliable but the model can
    drop items when asked to return several array entries at once — one call
    per factor sidesteps that failure mode entirely instead of working around
    it, at the cost of N sequential calls instead of one."""
    if not diagnosis.factors:
        return ExplainedDiagnosis(
            target_source_id=diagnosis.target_source_id, explained_factors=[], gaps=diagnosis.gaps
        )

    if client is None:
        return _fallback(
            diagnosis,
            Gap(
                description="LLM explanations were not generated for these factors.",
                reason="No LLM client is configured; using the rule-based summaries as-is.",
            ),
        )

    explained_factors: list[ExplainedFactor] = []
    any_fallback = False
    for factor in diagnosis.factors:
        candidate = await _explain_one_factor(factor, client=client, model=model)
        cites_only_known_ids = candidate is not None and set(candidate.cited_source_ids).issubset(
            set(factor.supporting_source_ids)
        )
        if candidate is not None and cites_only_known_ids:
            explained_factors.append(
                ExplainedFactor(
                    factor=factor, explanation=candidate.explanation, explanation_source="llm"
                )
            )
        else:
            any_fallback = True
            explained_factors.append(
                ExplainedFactor(
                    factor=factor, explanation=factor.summary, explanation_source="fallback"
                )
            )

    gaps = list(diagnosis.gaps)
    if any_fallback:
        gaps.append(
            Gap(
                description="One or more factor explanations fell back to the rule-based summary.",
                reason=(
                    "The model's explanation for that factor was missing or cited a record ID "
                    "outside the factor's own supporting evidence."
                ),
            )
        )

    return ExplainedDiagnosis(
        target_source_id=diagnosis.target_source_id, explained_factors=explained_factors, gaps=gaps
    )
