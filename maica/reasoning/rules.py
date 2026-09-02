from collections.abc import Sequence
from datetime import datetime
from typing import cast

from maica.graph.builder import (
    RecordLike,
    build_dependency_graph,
    field_value_node_id,
    record_node_id,
)
from maica.reasoning.models import DiagnosisResult, EvidenceItem, Factor, FactorLabel, Gap

# A value shared this widely is routine (a common GL account, a shared entity),
# so it isolates nothing about this transaction and is labelled as such rather
# than padding the list with a signal no one should act on.
_ROUTINE_SHARED_VALUE_THRESHOLD = 5

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


def _evidence_from(row: RecordLike) -> EvidenceItem:
    return EvidenceItem(
        source_id=row.source_id,
        record_type=row.record_type,
        field_name=row.field_name,
        old_value=row.old_value,
        new_value=row.new_value,
        actor=row.actor,
        context=row.context,
        occurred_at=row.occurred_at,
    )


def _is_modification(row: RecordLike) -> bool:
    """True when an existing value was altered, false when a blank field was
    populated for the first time. A memo being filled in is a weaker lead than
    an amount being changed, and the difference is visible in the evidence
    itself rather than assumed from the field's name."""
    return bool(row.old_value and row.old_value.strip())


def _change_label(row: RecordLike) -> FactorLabel:
    """How well documented the change itself is — never how likely it is to be
    the cause.

    A System Notes row carrying old value, new value, actor and timestamp is a
    complete audit entry: the consultant can open that record in NetSuite and
    see the same line. That the change happened is directly proven, so it is
    CONFIRMED. Drop any of those and the change is still supported but no
    longer fully documented, which is LIKELY.
    """
    fully_documented = bool(row.actor) and row.occurred_at is not None
    return FactorLabel.CONFIRMED if fully_documented else FactorLabel.LIKELY


def _build_change_factors(target_rows: Sequence[RecordLike], target_source_id: str) -> list[Factor]:
    """Field-change factors, from evidence that carries old_value (e.g. a
    System Notes export).

    The claim each factor makes is deliberately narrow: *this field changed,
    then, by them*. That claim an audit trail can prove outright. Whether the
    change caused the reported outcome is a separate question the evidence
    does not answer, and every summary says so — labelling a documented change
    CONFIRMED is not converting correlation into causation, because causation
    is not what is being claimed.
    """
    dated: list[tuple[bool, datetime | None, Factor]] = []
    for row in target_rows:
        if row.old_value is None:
            continue

        label = _change_label(row)
        opening = "Confirmed change" if label is FactorLabel.CONFIRMED else "Recorded change"
        if _is_modification(row):
            summary = (
                f"{opening}: {row.field_name} went from {row.old_value!r} to {row.new_value!r}"
            )
        else:
            summary = (
                f"{opening}: {row.field_name} was first set to {row.new_value!r} "
                "(no previous value recorded — this is a field being populated, "
                "not an existing value being altered)"
            )
        if row.actor:
            if row.actor.strip().lower() == "system":
                summary += ", recorded actor: System (an automated process, not a specific person)"
            else:
                summary += f", recorded actor: {row.actor}"
        if row.context:
            summary += f" (context: {row.context})"
        if row.occurred_at:
            summary += f" on {row.occurred_at.strftime('%d %b %Y %H:%M')}"

        if label is FactorLabel.CONFIRMED:
            summary += (
                ". The change itself is documented in the audit trail and can be "
                "checked on this record in NetSuite. That it caused the outcome is "
                "NOT established — compare the timing against when this transaction "
                f"posted and whether {row.field_name} affects downstream processing."
            )
        else:
            missing = "no actor was captured" if not row.actor else "no usable timestamp"
            summary += (
                f". The change is recorded but not fully documented — {missing} — so it "
                "cannot be placed against the posting time from this evidence alone."
            )

        dated.append(
            (
                _is_modification(row),
                row.occurred_at,
                Factor(
                    label=label,
                    rank=0,
                    summary=summary,
                    supporting_source_ids=[target_source_id],
                    evidence=[_evidence_from(row)],
                ),
            )
        )

    # Altering an existing value outranks populating an empty field, then most
    # recent first; rows with no parseable timestamp go last within each group.
    # This is read off the evidence (whether an old value exists), not off any
    # opinion about which NetSuite fields matter — see the note in diagnose().
    def _by_recency(
        group: list[tuple[bool, datetime | None, Factor]],
    ) -> list[tuple[bool, datetime | None, Factor]]:
        known = sorted(
            (entry for entry in group if entry[1] is not None),
            key=lambda entry: cast(datetime, entry[1]),
            reverse=True,
        )
        return known + [entry for entry in group if entry[1] is None]

    modifications = _by_recency([entry for entry in dated if entry[0]])
    first_values = _by_recency([entry for entry in dated if not entry[0]])
    return [factor for _, _, factor in (modifications + first_values)]


def _build_shared_value_factors(
    records: Sequence[RecordLike], target_rows: Sequence[RecordLike], target_source_id: str
) -> list[Factor]:
    """Factors from records that share a field value with the target — a
    structural correlation, never treated as a cause.

    These stay below CONFIRMED by design: sharing a value is not an event and
    nothing in the evidence proves the two records influenced each other. A
    value shared with only a handful of records is a usable lead (UNCERTAIN);
    one shared across many is routine and supports no conclusion at all
    (INSUFFICIENT_EVIDENCE), which is worth saying rather than ranking it as
    though it were a finding.
    """
    graph = build_dependency_graph(records)
    target_node = record_node_id(target_source_id)
    rows_by_source_id: dict[str, list[RecordLike]] = {}
    for row in records:
        rows_by_source_id.setdefault(row.source_id, []).append(row)

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

        routine = len(shared_ids) >= _ROUTINE_SHARED_VALUE_THRESHOLD
        label = FactorLabel.INSUFFICIENT_EVIDENCE if routine else FactorLabel.UNCERTAIN
        summary = (
            f"Correlation only: {row.field_name} = {row.new_value!r} is shared with "
            f"{len(shared_ids)} other record(s) — {', '.join(shared_ids)}."
        )
        if routine:
            summary += (
                " A value this widely shared is routine and isolates nothing about "
                "this transaction, so no conclusion should be drawn from it."
            )
        else:
            summary += (
                " Nothing here shows these records influenced each other — it is a "
                f"lead worth checking, not a finding. Look at whether something "
                f"affecting this {row.field_name} value explains the issue."
            )

        # The matching row on each related record is the proof of the shared
        # value; capped so a broad match does not flood the report.
        related_evidence = [
            _evidence_from(other)
            for shared_id in shared_ids[:5]
            for other in rows_by_source_id.get(shared_id, [])
            if other.field_name == row.field_name and other.new_value == row.new_value
        ]

        ranked_candidates.append(
            (
                len(shared_ids),
                Factor(
                    label=label,
                    rank=0,
                    summary=summary,
                    supporting_source_ids=[target_source_id, *shared_ids],
                    evidence=[_evidence_from(row), *related_evidence[:5]],
                ),
            )
        )

    # Tighter, more specific connections (fewer other records sharing the same
    # value) rank first — a value shared broadly (e.g. a common GL account) is
    # more likely routine and less likely to isolate this transaction.
    ranked_candidates.sort(key=lambda pair: pair[0])
    return [factor for _, factor in ranked_candidates]


def diagnose(records: Sequence[RecordLike], target_source_id: str) -> DiagnosisResult:
    """Deterministic, rule-based factor ranking — no LLM.

    Labels describe how well supported each factor's own claim is, and the
    claims are scoped so the strong labels stay honest:

    - CONFIRMED / LIKELY — a field change recorded in an audit trail. The
      claim is that the change happened, which the trail proves outright;
      whether it caused the outcome is never claimed.
    - UNCERTAIN — a shared field value. A real lead, but nothing shows the
      records influenced each other.
    - INSUFFICIENT_EVIDENCE — a value shared so widely it is routine and
      supports no conclusion.

    Never infers causation, and never blames a script/workflow/user without
    supporting evidence.

    Ordering within the change factors uses only what the evidence shows —
    whether an existing value was altered, and when. It does NOT weight fields
    by importance (amount over memo, say): that is a NetSuite domain judgement
    this module has no verified basis for, so it is left to the consultant
    reading the ranked list."""
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
