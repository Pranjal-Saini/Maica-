import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_current_user, get_db_session
from maica.auth.models import User
from maica.evidence import repository
from maica.evidence.models import Analysis
from maica.evidence.normalizer import get_normalizer
from maica.evidence.schemas import FileUploadResult, RawEvidenceRead, UploadResponse
from maica.ingest.errors import IngestValidationError
from maica.ingest.registry import AUTO_DETECT, detect_evidence_type, get_ingest_source
from maica.web.nav import page_context
from maica.web.templating import templates

router = APIRouter()


@router.get("/tenants/{tenant_id}/uploads/new", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    analysis_id: uuid.UUID | None = None,
) -> HTMLResponse:
    tenant = await repository.get_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request,
        "upload.html",
        page_context(
            user=user,
            active="evidence",
            tenant_id=tenant_id,
            tenant_name=tenant.name if tenant else None,
            analysis_id=analysis_id,
        ),
    )


async def _ingest_one_file(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    analysis: Analysis,
    filename: str,
    raw_input: bytes,
    evidence_type: str,
) -> FileUploadResult:
    if not raw_input.strip():
        return FileUploadResult(
            filename=filename,
            evidence_type=None,
            unrecognised_reason="This file is empty — nothing to read.",
        )

    resolved_type = (
        detect_evidence_type(raw_input) if evidence_type == AUTO_DETECT else evidence_type
    )
    if resolved_type is None:
        return FileUploadResult(
            filename=filename,
            evidence_type=None,
            unrecognised_reason=(
                "Could not tell which kind of NetSuite export this is from its column "
                "headers. Pick the evidence type explicitly, or check the file is a "
                "saved-search or System Notes export."
            ),
        )

    ingest_source = get_ingest_source(resolved_type)
    assert ingest_source is not None  # evidence_type is validated by the route

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

    return FileUploadResult(
        filename=filename,
        evidence_type=resolved_type,
        raw_evidence=RawEvidenceRead.model_validate(raw_evidence),
        records_created=records_created,
        normalization_notes=normalization_notes,
    )


@router.post("/tenants/{tenant_id}/uploads", response_model=UploadResponse)
async def upload_evidence(
    files: list[UploadFile],
    evidence_type: str = Form(AUTO_DETECT),
    analysis_id: uuid.UUID | None = Form(None),
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> UploadResponse:
    """Accepts one or more exports in a single upload. Each file's evidence
    type is detected from its own headers by default, so a saved-search export
    and a System Notes export can be dropped together and land in the same
    analysis."""
    if evidence_type != AUTO_DETECT and get_ingest_source(evidence_type) is None:
        raise IngestValidationError(f"unknown evidence_type '{evidence_type}'")

    analysis = None
    if analysis_id is not None:
        analysis = await repository.get_analysis(session, tenant_id, analysis_id)
    if analysis is None:
        analysis = await repository.create_analysis(session, tenant_id, created_by="upload")

    results: list[FileUploadResult] = []
    for upload in files:
        raw_input = await upload.read()
        results.append(
            await _ingest_one_file(
                session,
                tenant_id=tenant_id,
                analysis=analysis,
                filename=upload.filename or "(unnamed)",
                raw_input=raw_input,
                evidence_type=evidence_type,
            )
        )

    await session.commit()

    return UploadResponse(
        analysis_id=analysis.id,
        tenant_id=tenant_id,
        files=results,
        records_created=sum(r.records_created for r in results),
    )
