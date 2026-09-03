"""Comparing the records that went wrong against the ones that did not.

Everything else in this codebase answers "what is unusual here". That is the
best a tool can do when nobody has told it what wrong looks like — and it is
weak, because unusual is not wrong. An account's rarest behaviour is often
just its rarest behaviour.

A consultant investigating always knows the symptom: these invoices posted to
the wrong account, these bills skipped approval. Given that, the question
becomes answerable: what do the affected records have that the unaffected ones
do not? A key present on every affected record and no other is not a curiosity,
it is the difference between the two populations — which is as close to "the
problem" as evidence alone can honestly get.

It is still not causation. It is a measured difference between two groups the
consultant defined, and the counts behind it are always shown so they can
judge it themselves.

One GROUP BY over the analysis, so the work does not grow with the size of the
account.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.aggregates import _actor_class_case, _change_evidence_only
from maica.evidence.models import Record


@dataclass(frozen=True)
class ContrastRow:
    """One signature key, counted in both cohorts."""

    field_name: str
    actor_class: str
    context: str | None
    in_affected: int
    in_rest: int


@dataclass(frozen=True)
class CohortSizes:
    affected: int
    rest: int

    @property
    def total(self) -> int:
        return self.affected + self.rest


def _affected_ids_subquery(
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    *,
    record_ids: list[str] | None,
    field_name: str | None,
    value: str | None,
) -> Select:
    """The affected cohort, however the consultant described it.

    Both routes reduce to a set of source_ids, so everything downstream is
    identical — the reasoning never branches on how the symptom was stated.
    """
    # select(Record.source_id).distinct() rather than select(distinct(...)):
    # the latter labels the column distinct_1, and the subquery is referenced
    # by name downstream.
    stmt = (
        select(Record.source_id)
        .where(Record.tenant_id == tenant_id, Record.analysis_id == analysis_id)
        .distinct()
    )
    if record_ids:
        return stmt.where(Record.source_id.in_(record_ids))
    return stmt.where(Record.field_name == field_name, Record.new_value == value)


async def get_cohort_sizes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    *,
    record_ids: list[str] | None = None,
    field_name: str | None = None,
    value: str | None = None,
) -> CohortSizes:
    affected_ids = _affected_ids_subquery(
        tenant_id, analysis_id, record_ids=record_ids, field_name=field_name, value=value
    ).subquery()
    is_affected = Record.source_id.in_(select(affected_ids.c.source_id))

    stmt = select(
        func.count(distinct(case((is_affected, Record.source_id)))),
        func.count(distinct(case((~is_affected, Record.source_id)))),
    ).where(Record.tenant_id == tenant_id, Record.analysis_id == analysis_id)
    affected, rest = (await session.execute(stmt)).one()
    return CohortSizes(affected=affected or 0, rest=rest or 0)


async def compare_cohorts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    *,
    record_ids: list[str] | None = None,
    field_name: str | None = None,
    value: str | None = None,
) -> list[ContrastRow]:
    """Every change signature, counted in the affected cohort and outside it.

    Rows where a key is absent from the affected cohort are kept too: "none of
    the affected records went through the step all the others did" is as much a
    finding as the reverse, and dropping it would hide half the picture.
    """
    affected_ids = _affected_ids_subquery(
        tenant_id, analysis_id, record_ids=record_ids, field_name=field_name, value=value
    ).subquery()

    actor_class = _actor_class_case()
    keyed = (
        select(
            Record.source_id.label("source_id"),
            Record.field_name.label("field_name"),
            actor_class.label("actor_class"),
            Record.context.label("context"),
            Record.source_id.in_(select(affected_ids.c.source_id)).label("affected"),
        )
        .where(
            Record.tenant_id == tenant_id,
            Record.analysis_id == analysis_id,
            _change_evidence_only(),
            # An unrecorded actor is a hole in the export, not a property of a
            # record — the same exclusion the shortlist makes, for the same
            # reason. It would otherwise separate the cohorts by luck of which
            # rows happened to be complete.
            func.btrim(func.coalesce(Record.actor, "")) != "",
        )
        .distinct()
        .cte("contrast_keyed")
    )

    stmt = select(
        keyed.c.field_name,
        keyed.c.actor_class,
        keyed.c.context,
        func.count(case((keyed.c.affected, 1))),
        func.count(case((~keyed.c.affected, 1))),
    ).group_by(keyed.c.field_name, keyed.c.actor_class, keyed.c.context)
    return [
        ContrastRow(
            field_name=field_name_,
            actor_class=str(actor_class_),
            context=context,
            in_affected=in_affected,
            in_rest=in_rest,
        )
        for field_name_, actor_class_, context, in_affected, in_rest in (
            await session.execute(stmt)
        ).all()
    ]


def affected_predicate(
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    *,
    record_ids: list[str] | None = None,
    field_name: str | None = None,
    value: str | None = None,
) -> ColumnElement[bool]:
    """Reusable filter for listing the affected records themselves."""
    affected_ids = _affected_ids_subquery(
        tenant_id, analysis_id, record_ids=record_ids, field_name=field_name, value=value
    ).subquery()
    return and_(
        Record.tenant_id == tenant_id,
        Record.analysis_id == analysis_id,
        Record.source_id.in_(select(affected_ids.c.source_id)),
    )
