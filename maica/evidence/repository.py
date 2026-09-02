import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.models import Analysis, RawEvidence, Record, Tenant
from maica.evidence.normalizer import NormalizedRecordDraft
from maica.ingest.interface import IngestResult

# Every function here takes tenant_id explicitly and filters on it. There is no
# "get by id" without a tenant filter, and no update path for RawEvidence.


async def ensure_tenant(session: AsyncSession, tenant_id: uuid.UUID, name: str) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is not None:
        return tenant
    tenant = Tenant(id=tenant_id, name=name)
    session.add(tenant)
    await session.flush()
    return tenant


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


async def create_analysis(session: AsyncSession, tenant_id: uuid.UUID, created_by: str) -> Analysis:
    analysis = Analysis(tenant_id=tenant_id, created_by=created_by)
    session.add(analysis)
    await session.flush()
    return analysis


async def get_analysis(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID
) -> Analysis | None:
    stmt = select(Analysis).where(Analysis.id == analysis_id, Analysis.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_analyses_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Analysis]:
    stmt = (
        select(Analysis).where(Analysis.tenant_id == tenant_id).order_by(Analysis.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def store_raw_evidence(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    ingest_result: IngestResult,
) -> RawEvidence:
    raw_evidence = RawEvidence(
        tenant_id=tenant_id,
        analysis_id=analysis_id,
        source_type=ingest_result.request.source_type,
        request_made=ingest_result.request.request_detail,
        payload={"rows": ingest_result.rows},
        understood_summary={
            "rows_understood": ingest_result.rows_understood,
            "rows_skipped": ingest_result.rows_skipped,
            "columns_recognized": ingest_result.columns_recognized,
            "columns_ignored": ingest_result.columns_ignored,
            "skip_reasons": ingest_result.skip_reasons,
        },
        unavailable_reason=ingest_result.unavailable_reason,
    )
    session.add(raw_evidence)
    await session.flush()
    return raw_evidence


async def get_raw_evidence(
    session: AsyncSession, tenant_id: uuid.UUID, raw_evidence_id: uuid.UUID
) -> RawEvidence | None:
    stmt = select(RawEvidence).where(
        RawEvidence.id == raw_evidence_id, RawEvidence.tenant_id == tenant_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def store_records(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    raw_evidence_id: uuid.UUID,
    drafts: list[NormalizedRecordDraft],
) -> list[Record]:
    records = [
        Record(
            tenant_id=tenant_id,
            analysis_id=analysis_id,
            raw_evidence_id=raw_evidence_id,
            source_id=draft.source_id,
            record_type=draft.record_type,
            field_name=draft.field_name,
            old_value=draft.old_value,
            new_value=draft.new_value,
            actor=draft.actor,
            context=draft.context,
            occurred_at=draft.occurred_at,
        )
        for draft in drafts
    ]
    session.add_all(records)
    await session.flush()
    return records


async def get_records_for_analysis(
    session: AsyncSession, tenant_id: uuid.UUID, analysis_id: uuid.UUID
) -> list[Record]:
    stmt = select(Record).where(Record.tenant_id == tenant_id, Record.analysis_id == analysis_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@dataclass(frozen=True)
class TenantActivity:
    """What the client-account cards show at a glance. A tenant with no
    analyses yet is a normal state, not a missing row — callers get a zeroed
    entry rather than a KeyError."""

    analysis_count: int = 0
    last_analysis_at: datetime | None = None


async def get_activity_for_tenants(
    session: AsyncSession, tenant_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, TenantActivity]:
    """One grouped query for the whole dashboard, rather than a count per card."""
    if not tenant_ids:
        return {}

    stmt = (
        select(
            Analysis.tenant_id,
            func.count(Analysis.id),
            func.max(Analysis.created_at),
        )
        .where(Analysis.tenant_id.in_(tenant_ids))
        .group_by(Analysis.tenant_id)
    )
    result = await session.execute(stmt)
    activity = {
        tenant_id: TenantActivity(analysis_count=count, last_analysis_at=last_at)
        for tenant_id, count, last_at in result.all()
    }
    return {tenant_id: activity.get(tenant_id, TenantActivity()) for tenant_id in tenant_ids}
