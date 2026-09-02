import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import (
    get_authorized_tenant_id,
    get_current_user,
    get_db_session,
    get_llm_client,
)
from maica.auth.models import User
from maica.config.settings import get_settings
from maica.evidence import repository
from maica.graph.builder import build_dependency_graph
from maica.graph.render import render_text
from maica.reasoning.chat import ChatAnswer, ChatMessage, answer_question, build_evidence_context
from maica.reasoning.llm import ExplainedDiagnosis, explain_factors
from maica.reasoning.models import DiagnosisResult
from maica.reasoning.ollama_client import OllamaClient
from maica.reasoning.rules import diagnose, suggest_next_step
from maica.web.nav import page_context
from maica.web.templating import templates

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []


@router.get("/tenants/{tenant_id}/analyses", response_class=HTMLResponse)
async def list_tenant_analyses(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    analyses = await repository.get_analyses_for_tenant(session, tenant_id)
    tenant = await repository.get_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request,
        "analyses_list.html",
        page_context(
            request,
            user=user,
            active="analyses",
            tenant_id=tenant_id,
            tenant_name=tenant.name if tenant else None,
        )
        | {"analyses": analyses},
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    record_types_by_source_id: dict[str, str | None] = {}
    for record in records:
        record_types_by_source_id.setdefault(record.source_id, record.record_type)
    distinct_records = sorted(record_types_by_source_id.items())
    tenant = await repository.get_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request,
        "records_list.html",
        page_context(
            request,
            user=user,
            active="deep_dive",
            tenant_id=tenant_id,
            tenant_name=tenant.name if tenant else None,
            analysis_id=analysis_id,
        )
        | {"records": distinct_records},
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """Renders straight from diagnose(), which is deterministic and makes no
    model call, so the page is up immediately. The narration is fetched
    afterwards from /explain — a local model needs one call per factor and
    blocking the page on all of them made the report feel broken."""
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    diagnosis = diagnose(records, source_id)
    tenant = await repository.get_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request,
        "report.html",
        page_context(
            request,
            user=user,
            active="factors",
            tenant_id=tenant_id,
            tenant_name=tenant.name if tenant else None,
            analysis_id=analysis_id,
            source_id=source_id,
        )
        | {
            "factors": diagnosis.factors,
            "gaps": diagnosis.gaps,
            "next_step": suggest_next_step(diagnosis.factors),
        },
    )


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/chat", response_class=HTMLResponse)
async def chat_window(
    request: Request,
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """The chat in its own window. Opened from the composer on the report and
    evidence pages, so the conversation stops covering the report it is
    about."""
    tenant = await repository.get_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request,
        "chat_window.html",
        {
            "tenant_id": tenant_id,
            "analysis_id": analysis_id,
            "tenant_name": tenant.name if tenant else None,
        },
    )


@router.post("/tenants/{tenant_id}/analyses/{analysis_id}/chat", response_model=ChatAnswer)
async def chat_about_analysis(
    analysis_id: uuid.UUID,
    chat_request: ChatRequest,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
    client: OllamaClient = Depends(get_llm_client),
) -> ChatAnswer:
    """Answers a question grounded strictly in this analysis's own evidence.
    diagnose() is deterministic and does no model call, so running it per
    record just to build context is cheap."""
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    if not records:
        return ChatAnswer(
            answer=(
                "There's no evidence in this analysis yet. Upload a saved-search or "
                "System Notes export first, then ask me about it."
            ),
            grounded=False,
        )

    source_ids = sorted({record.source_id for record in records})
    diagnoses = [diagnose(records, source_id) for source_id in source_ids]
    evidence_context = build_evidence_context(records, diagnoses)

    return await answer_question(
        chat_request.question,
        evidence_context=evidence_context,
        history=chat_request.history,
        client=client,
        model=get_settings().llm_model,
    )
