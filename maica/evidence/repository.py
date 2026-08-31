import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.models import Analysis, RawEvidence, Tenant
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
