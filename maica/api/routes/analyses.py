import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_db_session, get_llm_client
from maica.config.settings import get_settings
from maica.evidence import repository
from maica.graph.builder import build_dependency_graph
from maica.graph.render import render_text
from maica.reasoning.llm import ExplainedDiagnosis, explain_factors
from maica.reasoning.models import DiagnosisResult
from maica.reasoning.ollama_client import OllamaClient
from maica.reasoning.rules import diagnose, suggest_next_step
from maica.web.templating import templates

router = APIRouter()


@router.get("/tenants/{tenant_id}/analyses", response_class=HTMLResponse)
async def list_tenant_analyses(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    analyses = await repository.get_analyses_for_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request, "analyses_list.html", {"tenant_id": tenant_id, "analyses": analyses}
    )


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/graph", response_class=PlainTextResponse)
async def get_analysis_graph(
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> str:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    if not records:
        return "No records found for this analysis."
    graph = build_dependency_graph(records)
    return render_text(graph, records)


@router.get(
    "/tenants/{tenant_id}/analyses/{analysis_id}/records/{source_id}/factors",
    response_model=DiagnosisResult,
)
async def get_record_factors(
    analysis_id: uuid.UUID,
    source_id: str,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DiagnosisResult:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    return diagnose(records, source_id)


@router.get(
    "/tenants/{tenant_id}/analyses/{analysis_id}/records/{source_id}/explain",
    response_model=ExplainedDiagnosis,
)
async def get_record_explanation(
    analysis_id: uuid.UUID,
    source_id: str,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
    client: OllamaClient = Depends(get_llm_client),
) -> ExplainedDiagnosis:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    diagnosis = diagnose(records, source_id)
    return await explain_factors(diagnosis, client=client, model=get_settings().llm_model)


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/records", response_class=HTMLResponse)
async def list_analysis_records(
    request: Request,
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    record_types_by_source_id: dict[str, str | None] = {}
    for record in records:
        record_types_by_source_id.setdefault(record.source_id, record.record_type)
    distinct_records = sorted(record_types_by_source_id.items())
    return templates.TemplateResponse(
        request,
        "records_list.html",
        {"tenant_id": tenant_id, "analysis_id": analysis_id, "records": distinct_records},
    )


@router.get(
    "/tenants/{tenant_id}/analyses/{analysis_id}/records/{source_id}/report",
    response_class=HTMLResponse,
)
async def get_record_report(
    request: Request,
    analysis_id: uuid.UUID,
    source_id: str,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
    client: OllamaClient = Depends(get_llm_client),
) -> HTMLResponse:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    diagnosis = diagnose(records, source_id)
    explained = await explain_factors(diagnosis, client=client, model=get_settings().llm_model)
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "tenant_id": tenant_id,
            "analysis_id": analysis_id,
            "source_id": source_id,
            "explained_factors": explained.explained_factors,
            "gaps": explained.gaps,
            "next_step": suggest_next_step(diagnosis.factors),
        },
    )
