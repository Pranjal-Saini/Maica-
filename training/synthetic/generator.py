"""Generates synthetic (DiagnosisResult, target explanations) pairs that
mirror the exact summary shapes maica/reasoning/rules.py produces (see
_build_change_factors and _build_shared_value_factors), for training data and
for evaluation of the narrator LLM.

A structured SyntheticFactorSpec is generated first; both the source summary
(matching rules.py's template) and the paraphrase target are rendered from
that same spec — never by string-parsing a summary back apart.
"""

import random
from dataclasses import dataclass, field
from enum import StrEnum

from maica.reasoning.llm import FactorExplanation
from maica.reasoning.models import DiagnosisResult, Factor, FactorLabel

from synthetic import templates as t


class FactorKind(StrEnum):
    CHANGE = "change"
    SHARED_VALUE = "shared_value"


@dataclass
class SyntheticFactorSpec:
    kind: FactorKind
    label: FactorLabel
    rank: int
    field_name: str
    new_value: str
    old_value: str | None = None
    actor: str | None = None
    context: str | None = None
    shared_ids: list[str] = field(default_factory=list)
    target_source_id: str = "1001"


def _supporting_ids(spec: SyntheticFactorSpec) -> list[str]:
    if spec.kind is FactorKind.CHANGE:
        return [spec.target_source_id]
    return [spec.target_source_id, *spec.shared_ids]


def render_summary(spec: SyntheticFactorSpec) -> str:
    """Matches maica/reasoning/rules.py's exact phrasing for the UNCERTAIN
    label; the other three labels are synthesized in the same structural
    shape (see templates.CHANGE_CERTAINTY_TAIL / SHARED_VALUE_CERTAINTY_TAIL)
    since rules.py does not produce them today."""
    if spec.kind is FactorKind.CHANGE:
        summary = f"{spec.field_name} changed from {spec.old_value!r} to {spec.new_value!r}"
        if spec.actor:
            if spec.actor.strip().lower() == "system":
                summary += ", recorded actor: System (an automated process, not a specific person)"
            else:
                summary += f", recorded actor: {spec.actor}"
        if spec.context:
            summary += f" (context: {spec.context})"
        tail = t.CHANGE_CERTAINTY_TAIL[spec.label].format(field_name=spec.field_name)
        return f"{summary}. {tail}"

    other_ids = ", ".join(spec.shared_ids)
    summary = (
        f"Shares {spec.field_name} = {spec.new_value!r} with {len(spec.shared_ids)} "
        f"other record(s): {other_ids}."
    )
    tail = t.SHARED_VALUE_CERTAINTY_TAIL[spec.label].format(field_name=spec.field_name)
    return f"{summary} {tail}"


def _actor_clause_for_paraphrase(spec: SyntheticFactorSpec) -> str:
    if not spec.actor:
        return ""
    if spec.actor.strip().lower() == "system":
        return ", recorded by an automated process rather than a specific person"
    return f", recorded by {spec.actor}"


def _context_clause_for_paraphrase(spec: SyntheticFactorSpec) -> str:
    return f" (execution context {spec.context})" if spec.context else ""


def render_paraphrase(spec: SyntheticFactorSpec, rng: random.Random, *, eval_mode: bool) -> str:
    if spec.kind is FactorKind.CHANGE:
        pool = t.CHANGE_PARAPHRASE_TEMPLATES_TRAIN
        if eval_mode:
            pool = pool + t.CHANGE_PARAPHRASE_TEMPLATES_EVAL_ONLY
        certainty = t.CHANGE_CERTAINTY_TAIL[spec.label].format(field_name=spec.field_name)
        template = rng.choice(pool)
        return template.format(
            field_name=spec.field_name,
            old_value=spec.old_value,
            new_value=spec.new_value,
            actor_clause=_actor_clause_for_paraphrase(spec),
            context_clause=_context_clause_for_paraphrase(spec),
            certainty=certainty,
            certainty_lower=certainty[0].lower() + certainty[1:],
        )

    pool = t.SHARED_VALUE_PARAPHRASE_TEMPLATES_TRAIN
    if eval_mode:
        pool = pool + t.SHARED_VALUE_PARAPHRASE_TEMPLATES_EVAL_ONLY
    certainty = t.SHARED_VALUE_CERTAINTY_TAIL[spec.label].format(field_name=spec.field_name)
    template = rng.choice(pool)
    return template.format(
        field_name=spec.field_name,
        new_value=spec.new_value,
        other_ids=", ".join(spec.shared_ids),
        certainty=certainty,
        certainty_lower=certainty[0].lower() + certainty[1:],
    )


def spec_to_factor(spec: SyntheticFactorSpec) -> Factor:
    return Factor(
        label=spec.label,
        rank=spec.rank,
        summary=render_summary(spec),
        supporting_source_ids=_supporting_ids(spec),
    )


def spec_to_target_explanation(
    spec: SyntheticFactorSpec, rng: random.Random, *, eval_mode: bool
) -> FactorExplanation:
    supporting = _supporting_ids(spec)
    if len(supporting) > 1 and rng.random() < 0.2:
        k = rng.randint(1, len(supporting) - 1)
        cited = rng.sample(supporting, k)
    else:
        cited = list(supporting)
    return FactorExplanation(
        factor_rank=spec.rank,
        explanation=render_paraphrase(spec, rng, eval_mode=eval_mode),
        cited_source_ids=cited,
    )


def generate_spec(
    rng: random.Random, *, rank: int, target_source_id: str, eval_mode: bool
) -> SyntheticFactorSpec:
    kind = rng.choice(list(FactorKind))
    label = rng.choice(list(FactorLabel))
    field_pool = t.FIELD_NAMES if eval_mode else t.TRAIN_FIELD_NAMES
    field_name = rng.choice(field_pool)
    values = t.VALUE_POOLS[field_name]

    if kind is FactorKind.CHANGE:
        old_value, new_value = rng.sample(values, 2) if len(values) >= 2 else (values[0], values[0])
        actor = rng.choice([None, "System", *t.ACTOR_NAMES])
        context = rng.choice([None, *t.CONTEXTS]) if actor else None
        return SyntheticFactorSpec(
            kind=kind,
            label=label,
            rank=rank,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            actor=actor,
            context=context,
            target_source_id=target_source_id,
        )

    new_value = rng.choice(values)
    num_shared = rng.randint(1, 3)
    shared_ids_set: set[str] = set()
    while len(shared_ids_set) < num_shared:
        candidate = str(1000 + rng.randint(1, 9000))
        if candidate != target_source_id:
            shared_ids_set.add(candidate)
    shared_ids = sorted(shared_ids_set)
    return SyntheticFactorSpec(
        kind=kind,
        label=label,
        rank=rank,
        field_name=field_name,
        new_value=new_value,
        shared_ids=shared_ids,
        target_source_id=target_source_id,
    )


def generate_diagnosis(
    rng: random.Random,
    *,
    num_factors: int,
    target_source_id: str = "1001",
    eval_mode: bool = False,
) -> tuple[DiagnosisResult, list[FactorExplanation], list[SyntheticFactorSpec]]:
    specs = [
        generate_spec(rng, rank=i, target_source_id=target_source_id, eval_mode=eval_mode)
        for i in range(1, num_factors + 1)
    ]
    factors = [spec_to_factor(s) for s in specs]
    targets = [spec_to_target_explanation(s, rng, eval_mode=eval_mode) for s in specs]
    diagnosis = DiagnosisResult(target_source_id=target_source_id, factors=factors, gaps=[])
    return diagnosis, targets, specs
