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
from maica.reasoning.chat import (
    MAX_RECORDS_IN_CHAT_CONTEXT,
    ChatAnswer,
    ChatMessage,
    answer_question,
    build_evidence_context,
    prioritise_source_ids,
)
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
    #: The record the consultant is looking at, when the chat was opened from a
    #: report. Decides what the evidence bundle covers first.
    focus_source_id: str | None = None


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

    The dependency graph is built once and reused across every record. It used
    to be rebuilt inside each diagnose() call, which on a 5,000-record account
    meant roughly half an hour of work before the model was even asked."""
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    if not records:
        return ChatAnswer(
            answer=(
                "There's no evidence in this analysis yet. Upload a saved-search or "
                "System Notes export first, then ask me about it."
            ),
            grounded=False,
        )

    graph = build_dependency_graph(records)
    all_source_ids = sorted({record.source_id for record in records})

    # Related records come from the focus record's own ranked factors, not from
    # raw graph adjacency. Adjacency includes every record sharing a structural
    # value (a currency, a subsidiary), which on a real account is most of them
    # and prioritises nothing. The ranking has already discarded those.
    focus = chat_request.focus_source_id
    focus_diagnosis = (
        diagnose(records, focus, graph=graph)
        if focus is not None and focus in set(all_source_ids)
        else None
    )
    related = (
        sorted(
            {
                source_id
                for factor in focus_diagnosis.factors
                for source_id in factor.supporting_source_ids
            }
        )
        if focus_diagnosis
        else []
    )

    ordered_ids = prioritise_source_ids(all_source_ids, focus, related)
    diagnoses = [
        focus_diagnosis
        if focus_diagnosis is not None and source_id == focus
        else diagnose(records, source_id, graph=graph)
        for source_id in ordered_ids[:MAX_RECORDS_IN_CHAT_CONTEXT]
    ]
    evidence_context = build_evidence_context(
        records,
        diagnoses,
        records_in_analysis=len(all_source_ids),
        focus_source_id=focus,
    )

    return await answer_question(
        chat_request.question,
        evidence_context=evidence_context,
        history=chat_request.history,
        client=client,
        model=get_settings().llm_model,
    )
