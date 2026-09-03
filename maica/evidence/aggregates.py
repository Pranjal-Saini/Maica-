"""Grouped counts over an analysis's records.

The deep-dive page groups an analysis's changes instead of listing every
record, so every number it shows is a GROUP BY. Loading 52,000 Record rows to
count them in Python is the same shape of mistake that once made a
5,000-record account unusable, so none of that happens here.

Nothing on this path calls diagnose(). That is deliberate rather than
incidental: a per-record reasoning loop is exactly what took one operation to
half an hour, and an aggregate page structurally cannot reintroduce it.

Kept apart from repository.py because that module owns row-level reads and
writes; this one only ever counts. Both take tenant_id explicitly and filter on
it, with no "get by id" that skips the tenant.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Case, ColumnElement, and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.models import Record


@dataclass(frozen=True)
class PatternRow:
    field_name: str
    change_kind: str
    actor_class: str
    context: str | None
    record_count: int
    change_count: int
    actors: tuple[str, ...]
    first_seen: datetime | None
    last_seen: datetime | None
    day_count: int


@dataclass(frozen=True)
class FieldTotal:
    field_name: str
    record_count: int
    change_count: int


@dataclass(frozen=True)
class ValueFacetRow:
    field_name: str
    distinct_values: int
    largest_value_count: int


def _actor_class_case() -> Case:
    """The SQL twin of reasoning.patterns.classify_actor.

    Grouping by the class in SQL, rather than collapsing raw actors afterwards,
    keeps COUNT(DISTINCT source_id) exact — summing per-actor groups would
    count a record twice when two different people touched the same field.
    """
    trimmed = func.btrim(func.coalesce(Record.actor, ""))
    return case(
        (trimmed == "", "unattributed"),
        (func.lower(trimmed) == "system", "System"),
        else_="user",
    )


def _change_kind_case() -> Case:
    """The SQL twin of reasoning.patterns.classify_change."""
    return case(
        (func.btrim(func.coalesce(Record.old_value, "")) != "", "modified"),
        else_="first set",
    )


def _change_evidence_only() -> ColumnElement[bool]:
    # old_value is populated only by a change-history source; a saved-search
    # snapshot always leaves it NULL (see evidence/normalizer.py).
    return Record.old_value.isnot(None)


def change_pattern_predicate(
    *, field_name: str, change_kind: str, actor_class: str, context: str | None
) -> ColumnElement[bool]:
    """The drill-down filter, built from the same expressions as the aggregate.

    Sharing them is what stops the count printed on a card and the length of
    the list behind it from drifting apart.
    """
    clauses = [
        Record.field_name == field_name,
        _change_kind_case() == change_kind,
        _actor_class_case() == actor_class,
        _change_evidence_only(),
    ]
    clauses.append(Record.context.is_(None) if context is None else Record.context == context)
    return and_(*clauses)


async def get_change_pattern_rows(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID
) -> list[PatternRow]:
    actor_class = _actor_class_case()
    change_kind = _change_kind_case()
    stmt = (
        select(
            Record.field_name,
            change_kind.label("change_kind"),
            actor_class.label("actor_class"),
            Record.context,
            func.count(distinct(Record.source_id)),
            func.count(Record.id),
            func.array_agg(distinct(Record.actor)),
            func.min(Record.occurred_at),
            func.max(Record.occurred_at),
            func.count(distinct(func.date_trunc("day", Record.occurred_at))),
        )
        .where(
            Record.tenant_id == tenant_id,
            Record.analysis_id == analysis_id,
            _change_evidence_only(),
        )
        .group_by(Record.field_name, change_kind, actor_class, Record.context)
    )
    result = await session.execute(stmt)
    return [
        PatternRow(
            field_name=field_name,
            change_kind=str(kind),
            actor_class=str(klass),
            context=context,
            record_count=record_count,
            change_count=change_count,
            actors=tuple(sorted(a for a in (actors or []) if a and a.strip())),
            first_seen=first_seen,
            last_seen=last_seen,
            day_count=day_count or 0,
        )
        for (
            field_name,
            kind,
            klass,
            context,
            record_count,
            change_count,
            actors,
            first_seen,
            last_seen,
            day_count,
        ) in result.all()
    ]


async def get_field_totals(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID
) -> list[FieldTotal]:
    stmt = (
        select(
            Record.field_name,
            func.count(distinct(Record.source_id)),
            func.count(Record.id),
        )
        .where(
            Record.tenant_id == tenant_id,
            Record.analysis_id == analysis_id,
            _change_evidence_only(),
        )
        .group_by(Record.field_name)
    )
    result = await session.execute(stmt)
    return [
        FieldTotal(field_name=field_name, record_count=record_count, change_count=change_count)
        for field_name, record_count, change_count in result.all()
    ]


async def get_records_matching(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    predicate: ColumnElement[bool],
    *,
    limit: int,
    offset: int,
) -> tuple[list[tuple[str, str | None, int]], int]:
    """One page of the records behind a pattern, plus the true total.

    The total is re-counted here and never taken from the URL.
    """
    where = (Record.tenant_id == tenant_id, Record.analysis_id == analysis_id, predicate)

    total = int(
        (
            await session.execute(select(func.count(distinct(Record.source_id))).where(*where))
        ).scalar_one()
        or 0
    )
    page_stmt = (
        select(Record.source_id, func.min(Record.record_type), func.count(Record.id))
        .where(*where)
        .group_by(Record.source_id)
        .order_by(Record.source_id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(page_stmt)).all()
    return [(source_id, record_type, changes) for source_id, record_type, changes in rows], total


async def source_id_exists(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID, source_id: str
) -> bool:
    """Backs the jump-to-record box on the deep dive."""
    stmt = select(Record.id).where(
        Record.tenant_id == tenant_id,
        Record.analysis_id == analysis_id,
        Record.source_id == source_id,
    )
    return (await session.execute(stmt.limit(1))).first() is not None


async def get_value_facet_rows(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID
) -> list[ValueFacetRow]:
    """Per-field value spread, for analyses that carry no change history.

    A saved-search export can still be grouped — by the values it holds — but
    only on fields whose values actually divide the account. Which those are is
    decided by reasoning.patterns from these counts, not here.
    """
    per_value = (
        select(
            Record.field_name.label("field_name"),
            func.count(distinct(Record.source_id)).label("record_count"),
        )
        .where(
            Record.tenant_id == tenant_id,
            Record.analysis_id == analysis_id,
            Record.new_value.isnot(None),
            func.btrim(Record.new_value) != "",
        )
        .group_by(Record.field_name, Record.new_value)
        .subquery()
    )
    stmt = (
        select(
            per_value.c.field_name,
            func.count(),
            func.max(per_value.c.record_count),
        )
        .group_by(per_value.c.field_name)
        .order_by(func.max(per_value.c.record_count).desc(), per_value.c.field_name)
    )
    result = await session.execute(stmt)
    return [
        ValueFacetRow(
            field_name=field_name,
            distinct_values=distinct_values,
            largest_value_count=largest_value_count,
        )
        for field_name, distinct_values, largest_value_count in result.all()
    ]


@dataclass(frozen=True)
class AnalysisTotals:
    records: int
    records_with_change_evidence: int
    unattributed_change_rows: int


async def get_analysis_totals(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID
) -> AnalysisTotals:
    """Three numbers the deep dive needs, in one scan.

    They were three separate queries, each re-reading the whole analysis. At
    12,000 records that was ~0.7s of pure duplication — the aggregate is a
    sequential scan either way, so the only saving available is doing fewer of
    them. (A covering index was measured and made it worse: Postgres is right
    to seq-scan when the aggregate touches most of the table.)
    """
    change_row = _change_evidence_only()
    stmt = select(
        func.count(distinct(Record.source_id)),
        func.count(distinct(case((change_row, Record.source_id)))),
        func.count(case((and_(change_row, func.btrim(func.coalesce(Record.actor, "")) == ""), 1))),
    ).where(Record.tenant_id == tenant_id, Record.analysis_id == analysis_id)
    records, with_changes, unattributed = (await session.execute(stmt)).one()
    return AnalysisTotals(
        records=records or 0,
        records_with_change_evidence=with_changes or 0,
        unattributed_change_rows=unattributed or 0,
    )
