import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_db_session
from maica.evidence import repository
from maica.evidence.normalizer import get_normalizer
from maica.evidence.schemas import RawEvidenceRead, UploadResponse
from maica.ingest.errors import IngestValidationError
from maica.ingest.registry import get_ingest_source
from maica.web.templating import templates

router = APIRouter()


@router.get("/tenants/{tenant_id}/uploads/new", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    analysis_id: uuid.UUID | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "upload.html", {"tenant_id": tenant_id, "analysis_id": analysis_id}
    )


@router.post("/tenants/{tenant_id}/uploads", response_model=UploadResponse)
async def upload_saved_search(
    file: UploadFile,
    evidence_type: str = Form("saved_search_csv"),
    analysis_id: uuid.UUID | None = Form(None),
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> UploadResponse:
    ingest_source = get_ingest_source(evidence_type)
    if ingest_source is None:
        raise IngestValidationError(f"unknown evidence_type '{evidence_type}'")

    raw_input = await file.read()

    analysis = None
    if analysis_id is not None:
        analysis = await repository.get_analysis(session, tenant_id, analysis_id)
    if analysis is None:
        analysis = await repository.create_analysis(session, tenant_id, created_by="upload")

    ingest_result = ingest_source.ingest(raw_input)
    raw_evidence = await repository.store_raw_evidence(
        session, tenant_id, analysis.id, ingest_result
    )

    records_created = 0
    normalization_notes: list[str] = []
    normalizer = get_normalizer(raw_evidence.source_type)
    if normalizer is not None:
        drafts, norm_result = normalizer.normalize(raw_evidence)
        await repository.store_records(session, tenant_id, analysis.id, raw_evidence.id, drafts)
        records_created = norm_result.records_created
        normalization_notes = norm_result.notes

    await session.commit()

    return UploadResponse(
        raw_evidence=RawEvidenceRead.model_validate(raw_evidence),
        records_created=records_created,
        normalization_notes=normalization_notes,
    )
