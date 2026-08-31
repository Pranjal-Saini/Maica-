import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_current_tenant_id, get_db_session
from maica.evidence import repository
from maica.graph.builder import build_dependency_graph
from maica.graph.render import render_text
from maica.reasoning.models import DiagnosisResult
from maica.reasoning.rules import diagnose

router = APIRouter()


@router.get("/analyses/{analysis_id}/graph", response_class=PlainTextResponse)
async def get_analysis_graph(
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> str:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    if not records:
        return "No records found for this analysis."
    graph = build_dependency_graph(records)
    return render_text(graph, records)


@router.get("/analyses/{analysis_id}/records/{source_id}/factors", response_model=DiagnosisResult)
async def get_record_factors(
    analysis_id: uuid.UUID,
    source_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DiagnosisResult:
    records = await repository.get_records_for_analysis(session, tenant_id, analysis_id)
    return diagnose(records, source_id)
