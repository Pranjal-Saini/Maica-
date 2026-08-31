import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence import repository
from maica.evidence.normalizer import get_normalizer
from maica.ingest.csv_saved_search import CsvSavedSearchSource


async def test_tenant_cannot_read_another_tenants_raw_evidence(db_session: AsyncSession) -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    await repository.ensure_tenant(db_session, tenant_a, name="tenant-a")
    await repository.ensure_tenant(db_session, tenant_b, name="tenant-b")

    analysis = await repository.create_analysis(db_session, tenant_a, created_by="test")
    ingest_result = CsvSavedSearchSource().ingest(b"Internal ID,Date\n1,1/1/2026\n")
    raw_evidence = await repository.store_raw_evidence(
        db_session, tenant_a, analysis.id, ingest_result
    )
    await db_session.commit()

    assert await repository.get_raw_evidence(db_session, tenant_a, raw_evidence.id) is not None
    assert await repository.get_raw_evidence(db_session, tenant_b, raw_evidence.id) is None


async def test_tenant_cannot_read_another_tenants_records(db_session: AsyncSession) -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    await repository.ensure_tenant(db_session, tenant_a, name="tenant-a")
    await repository.ensure_tenant(db_session, tenant_b, name="tenant-b")

    analysis = await repository.create_analysis(db_session, tenant_a, created_by="test")
    ingest_result = CsvSavedSearchSource().ingest(b"Internal ID,Date,Amount\n1,1/1/2026,500\n")
    raw_evidence = await repository.store_raw_evidence(
        db_session, tenant_a, analysis.id, ingest_result
    )
    normalizer = get_normalizer(raw_evidence.source_type)
    assert normalizer is not None
    drafts, _ = normalizer.normalize(raw_evidence)
    await repository.store_records(db_session, tenant_a, analysis.id, raw_evidence.id, drafts)
    await db_session.commit()

    assert len(await repository.get_records_for_analysis(db_session, tenant_a, analysis.id)) > 0
    assert await repository.get_records_for_analysis(db_session, tenant_b, analysis.id) == []
