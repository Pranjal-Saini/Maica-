"""Which records to open first, ranked across a whole analysis.

`diagnose()` ranks factors inside one record, which only helps once you already
know which record to open. On an account with 10,000 of them that is the whole
problem, and grouping them into patterns organises the pile without reducing it.

This module ranks the records themselves, by how unlike the rest of the account
each one is. Every term is a count taken from this analysis, so nothing assumes
NetSuite semantics and the measure recalibrates itself on a differently
customised account.

    weight(key) = -ln(n / N) * ln(1 + n)
    score(record) = sum of weight over the record's distinct keys

`n` is how many records share a key, `N` how many records there are. The first
factor is unusualness — a key on nearly every record contributes ~0, because
`-ln(1)` is 0, so the account's routine is free. The second is reach, and it is
what stops a key seen exactly once from winning: a lone key is usually export
noise rather than a finding. Their product peaks for keys that are rare but not
unique, which is where a consultant should actually start.

It is one aggregate query. No Python loop over records, no diagnose(), no
graph — a per-record loop here is the exact shape that once turned a single
operation into half an hour on a 5,000-record account.
"""

import math
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import CTE, Float, Join, String, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.aggregates import _actor_class_case, _change_evidence_only
from maica.evidence.models import Record

#: Records named at the top of an analysis. Deliberately small — the point is
#: to hand over a shortlist, not a shorter pile.
SHORTLIST_LIMIT = 8

#: Reasons shown per shortlisted record before the rest are summarised.
MAX_REASONS_PER_RECORD = 3

KEY_CHANGE = "change"
KEY_VALUE = "value"


@dataclass(frozen=True)
class ShortlistReason:
    """One signature key that pushed a record up the list, with the counts that
    make it checkable."""

    field_name: str
    actor_class: str | None
    context: str | None
    value: str | None
    records_sharing: int
    total_records: int

    @property
    def share(self) -> float:
        return self.records_sharing / self.total_records if self.total_records else 0.0

    @property
    def weight(self) -> float:
        return _weight(self.records_sharing, self.total_records)


@dataclass(frozen=True)
class ShortlistEntry:
    source_id: str
    record_type: str | None
    score: float
    key_count: int
    reasons: tuple[ShortlistReason, ...]
    hidden_reason_count: int = 0


@dataclass(frozen=True)
class Shortlist:
    entries: tuple[ShortlistEntry, ...]
    key_kind: str
    total_records: int
    #: Change rows excluded from scoring because no actor was recorded on them.
    unattributed_rows: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.entries


def _weight(records_sharing: int, total_records: int) -> float:
    """The scoring function, in Python, so it can be unit-tested without a
    database and compared against what SQL produces."""
    if total_records <= 0 or records_sharing <= 0:
        return 0.0
    share = min(records_sharing / total_records, 1.0)
    return -math.log(share) * math.log(1 + records_sharing)


def _keyed_cte(tenant_id: uuid.UUID, analysis_id: uuid.UUID, *, key_kind: str) -> CTE:
    """One row per (record, distinct signature key).

    `context` and `value` are coalesced to '' rather than left NULL: a SQL join
    on a NULL key matches nothing, which would silently drop every record whose
    export carried no context — the exact evidence a partial export produces.
    """
    where = [Record.tenant_id == tenant_id, Record.analysis_id == analysis_id]
    # Typed loosely because the two branches are different SQL expression
    # classes that only have ColumnElement in common.
    actor_class: Any
    context: Any
    value: Any
    if key_kind == KEY_CHANGE:
        where.append(_change_evidence_only())
        # A row whose export recorded no actor is a hole in the evidence, not a
        # property of the record. Scoring it made records rank highly because
        # their export was patchy — turning a gap into a signal, which is the
        # opposite of what data-rules.md asks for. Such rows still appear in the
        # pattern index, where they are reported as what they are.
        where.append(func.btrim(func.coalesce(Record.actor, "")) != "")
        actor_class = _actor_class_case()
        context = func.coalesce(Record.context, "")
        value = literal("", String)
    else:
        # No change history at all, so the only thing left to key on is which
        # values a record holds.
        where.append(Record.new_value.isnot(None))
        where.append(func.btrim(Record.new_value) != "")
        actor_class = literal("", String)
        context = literal("", String)
        value = Record.new_value

    return (
        select(
            Record.source_id.label("source_id"),
            Record.field_name.label("field_name"),
            actor_class.label("actor_class"),
            context.label("context"),
            value.label("value"),
        )
        .where(*where)
        .distinct()
        .cte(f"keyed_{key_kind}")
    )


def _key_counts_cte(keyed: CTE) -> CTE:
    return (
        select(
            keyed.c.field_name,
            keyed.c.actor_class,
            keyed.c.context,
            keyed.c.value,
            func.count().label("n"),
        )
        .group_by(keyed.c.field_name, keyed.c.actor_class, keyed.c.context, keyed.c.value)
        .cte("key_counts")
    )


def _join(keyed: CTE, counts: CTE) -> Join:
    return keyed.join(
        counts,
        (keyed.c.field_name == counts.c.field_name)
        & (keyed.c.actor_class == counts.c.actor_class)
        & (keyed.c.context == counts.c.context)
        & (keyed.c.value == counts.c.value),
    )


async def get_shortlist(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    *,
    total_records: int,
    has_change_evidence: bool,
    unattributed_rows: int = 0,
    limit: int = SHORTLIST_LIMIT,
) -> Shortlist:
    key_kind = KEY_CHANGE if has_change_evidence else KEY_VALUE
    unattributed = unattributed_rows if key_kind == KEY_CHANGE else 0
    if total_records <= 0:
        return Shortlist(entries=(), key_kind=key_kind, total_records=total_records)

    keyed = _keyed_cte(tenant_id, analysis_id, key_kind=key_kind)
    counts = _key_counts_cte(keyed)

    # count() is bigint and Postgres does integer division, so the cast is
    # load-bearing: without it n/N is 0 for every key and every score is 0.
    share = cast(counts.c.n, Float) / float(total_records)
    weight = -func.ln(share) * func.ln(1 + counts.c.n)

    scored = (
        select(
            keyed.c.source_id.label("source_id"),
            func.sum(weight).label("score"),
            func.count().label("key_count"),
        )
        .select_from(_join(keyed, counts))
        .group_by(keyed.c.source_id)
        .order_by(func.sum(weight).desc(), keyed.c.source_id)
        .limit(limit)
        .cte("scored")
    )

    # The ranking and the reasons behind it come back from one statement. Run as
    # two, each re-derived `keyed` — a DISTINCT over every row in the analysis —
    # and did it twice for the same answer.
    stmt = (
        select(
            scored.c.source_id,
            scored.c.score,
            scored.c.key_count,
            keyed.c.field_name,
            keyed.c.actor_class,
            keyed.c.context,
            keyed.c.value,
            counts.c.n,
        )
        .select_from(_join(keyed, counts).join(scored, scored.c.source_id == keyed.c.source_id))
        .order_by(scored.c.score.desc(), scored.c.source_id)
    )

    scores: dict[str, tuple[float, int]] = {}
    reasons: dict[str, list[ShortlistReason]] = {}
    for source_id, score, key_count, field_name, actor_class, context, value, n in (
        await session.execute(stmt)
    ).all():
        scores.setdefault(source_id, (float(score or 0.0), key_count))
        reasons.setdefault(source_id, []).append(
            ShortlistReason(
                field_name=field_name,
                actor_class=actor_class or None,
                context=context or None,
                value=value or None,
                records_sharing=n,
                total_records=total_records,
            )
        )

    if not scores:
        return Shortlist(
            entries=(),
            key_kind=key_kind,
            total_records=total_records,
            unattributed_rows=unattributed,
        )

    ranked = sorted(scores, key=lambda source_id: (-scores[source_id][0], source_id))
    record_types = await _record_types_for(session, tenant_id, analysis_id, ranked)

    entries: list[ShortlistEntry] = []
    for source_id in ranked:
        score, key_count = scores[source_id]
        found = sorted(reasons[source_id], key=lambda r: (-r.weight, r.field_name))
        entries.append(
            ShortlistEntry(
                source_id=source_id,
                record_type=record_types.get(source_id),
                score=score,
                key_count=key_count,
                reasons=tuple(found[:MAX_REASONS_PER_RECORD]),
                hidden_reason_count=max(0, len(found) - MAX_REASONS_PER_RECORD),
            )
        )
    return Shortlist(
        entries=tuple(entries),
        key_kind=key_kind,
        total_records=total_records,
        unattributed_rows=unattributed,
    )


async def _record_types_for(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID, source_ids: list[str]
) -> dict[str, str | None]:
    stmt = (
        select(Record.source_id, func.min(Record.record_type))
        .where(
            Record.tenant_id == tenant_id,
            Record.analysis_id == analysis_id,
            Record.source_id.in_(source_ids),
        )
        .group_by(Record.source_id)
    )
    return {
        source_id: record_type for source_id, record_type in (await session.execute(stmt)).all()
    }
