import uuid

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_current_tenant_id, get_db_session
from maica.evidence import repository
from maica.evidence.normalizer import get_normalizer
from maica.evidence.schemas import RawEvidenceRead, UploadResponse
from maica.ingest.csv_saved_search import CsvSavedSearchSource

router = APIRouter()
templates = Jinja2Templates(directory="maica/web/templates")


@router.get("/uploads/new", response_class=HTMLResponse)
async def upload_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html", {})


@router.post("/uploads", response_model=UploadResponse)
async def upload_saved_search(
    file: UploadFile,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> UploadResponse:
    raw_input = await file.read()

    await repository.ensure_tenant(session, tenant_id, name="dev-tenant")
    analysis = await repository.create_analysis(session, tenant_id, created_by="upload")

    ingest_result = CsvSavedSearchSource().ingest(raw_input)
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
