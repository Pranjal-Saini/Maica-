from collections.abc import Sequence
from datetime import datetime
from typing import cast

from maica.graph.builder import (
    RecordLike,
    build_dependency_graph,
    field_value_node_id,
    record_node_id,
)
from maica.reasoning.models import DiagnosisResult, Factor, FactorLabel, Gap

_NO_CHANGE_EVIDENCE_GAP = Gap(
    description=(
        "No script, workflow, integration, or configuration-change evidence was "
        "ingested for this record."
    ),
    reason=(
        "Only a saved-search CSV export (a snapshot, not a change history) was "
        "uploaded for this record. Upload a System Notes export, script "
        "deployment list, or execution log to check for automation causes."
    ),
)


def _build_change_factors(target_rows: Sequence[RecordLike], target_source_id: str) -> list[Factor]:
    """Field-change factors, from evidence that carries old_value (e.g. a
    System Notes export) — a direct, confirmed fact about what changed on
    this record, not merely a correlation with another record. Still never
    asserted as a cause: a change is not proof of causing the outcome."""
    dated: list[tuple[datetime | None, Factor]] = []
    for row in target_rows:
        if row.old_value is None:
            continue

        summary = f"{row.field_name} changed from {row.old_value!r} to {row.new_value!r}"
        if row.actor:
            if row.actor.strip().lower() == "system":
                summary += ", recorded actor: System (an automated process, not a specific person)"
            else:
                summary += f", recorded actor: {row.actor}"
        if row.context:
            summary += f" (context: {row.context})"
        summary += (
            ". A field change alone does not confirm it caused the outcome — check "
            "the timing against when this transaction posted and whether "
            f"{row.field_name} affects downstream processing."
        )

        dated.append(
            (
                row.occurred_at,
                Factor(
                    label=FactorLabel.UNCERTAIN,
                    rank=0,
                    summary=summary,
                    supporting_source_ids=[target_source_id],
                ),
            )
        )

    # Most recent change first; rows with no parseable timestamp go last.
    known = sorted(
        (pair for pair in dated if pair[0] is not None),
        key=lambda pair: cast(datetime, pair[0]),
        reverse=True,
    )
    unknown = [pair for pair in dated if pair[0] is None]
    return [factor for _, factor in (known + unknown)]


def _build_shared_value_factors(
    records: Sequence[RecordLike], target_rows: Sequence[RecordLike], target_source_id: str
) -> list[Factor]:
    """UNCERTAIN factors from records that share a field value with the target
    — a structural correlation, never treated as a cause on its own."""
    graph = build_dependency_graph(records)
    target_node = record_node_id(target_source_id)

    ranked_candidates: list[tuple[int, Factor]] = []
    for row in target_rows:
        if not row.new_value:
            continue
        node_id = field_value_node_id(row.field_name, row.new_value)
        if not graph.has_node(node_id):
            continue
        shared_ids = sorted(
            node.removeprefix("record:") for node in graph.neighbors(node_id) if node != target_node
        )
        if not shared_ids:
            continue
        summary = (
            f"Shares {row.field_name} = {row.new_value!r} with {len(shared_ids)} "
            f"other record(s): {', '.join(shared_ids)}. This is a correlation, "
            f"not a confirmed cause — investigate whether something affecting "
            f"this {row.field_name} value explains the issue."
        )
        ranked_candidates.append(
            (
                len(shared_ids),
                Factor(
                    label=FactorLabel.UNCERTAIN,
                    rank=0,
                    summary=summary,
                    supporting_source_ids=[target_source_id, *shared_ids],
                ),
            )
        )

    # Tighter, more specific connections (fewer other records sharing the same
    # value) rank first — a value shared broadly (e.g. a common GL account) is
    # more likely routine and less likely to isolate this transaction.
    ranked_candidates.sort(key=lambda pair: pair[0])
    return [factor for _, factor in ranked_candidates]


def diagnose(records: Sequence[RecordLike], target_source_id: str) -> DiagnosisResult:
    """Deterministic, rule-based factor ranking — no LLM. Only ever reasons
    from what the evidence directly shows: confirmed field changes (when
    change-history evidence exists), shared field values, and named gaps.
    Never infers causation, and never blames a script/workflow/user without
    supporting evidence."""
    target_rows = [row for row in records if row.source_id == target_source_id]

    if not target_rows:
        return DiagnosisResult(
            target_source_id=target_source_id,
            factors=[],
            gaps=[
                Gap(
                    description=f"No record with source_id '{target_source_id}' was found.",
                    reason="Not present in this analysis's ingested evidence.",
                )
            ],
        )

    change_factors = _build_change_factors(target_rows, target_source_id)
    shared_value_factors = _build_shared_value_factors(records, target_rows, target_source_id)

    factors = [*change_factors, *shared_value_factors]
    for position, factor in enumerate(factors, start=1):
        factor.rank = position

    gaps: list[Gap] = []
    if not shared_value_factors:
        gaps.append(
            Gap(
                description="No shared-field relationships found for this record.",
                reason=(
                    "None of this record's field values match another record in "
                    "this analysis, so no correlations could be surfaced from "
                    "this evidence."
                ),
            )
        )

    if not any(row.actor for row in target_rows):
        gaps.append(
            Gap(
                description="No actor/user information is available for this record.",
                reason=(
                    "The uploaded export did not include a 'created by', "
                    "'last modified by', or 'set by' column."
                ),
            )
        )

    if all(row.occurred_at is None for row in target_rows):
        gaps.append(
            Gap(
                description="This record's date could not be placed on a timeline.",
                reason="occurred_at was missing or unparseable for every field on this record.",
            )
        )

    if not change_factors:
        gaps.append(_NO_CHANGE_EVIDENCE_GAP)

    return DiagnosisResult(target_source_id=target_source_id, factors=factors, gaps=gaps)


def suggest_next_step(factors: Sequence[Factor]) -> str:
    """One deterministic, actionable suggestion — not the LLM's job, since it
    must stay consistent regardless of whether the LLM step ran or fell back."""
    if factors:
        top = factors[0]
        return (
            f"Start with the top-ranked factor (rank {top.rank}): {top.summary} "
            "Pull these records up side by side in NetSuite and compare them."
        )
    return (
        "No correlations were found in this evidence. The next useful step is "
        "uploading a System Notes export, script deployment list, or execution "
        "log for this account — this ingestion path alone cannot show what "
        "changed or which automation ran."
    )
