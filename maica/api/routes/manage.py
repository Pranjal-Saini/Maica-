"""Exporting an analysis, and deleting what MAICA holds.

These are the only routes that remove stored data, so they live together
rather than being scattered through the read paths. Client NetSuite access is
untouched by all of them: deleting a client account here removes MAICA's copy
of the evidence and nothing in the ERP, which is worth being able to say
plainly to a client's administrator.

Deletes are POSTs, not DELETEs, because they are driven by plain HTML forms —
the confirmation is native and works without JavaScript.
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_current_user, get_db_session
from maica.auth import repository as auth_repository
from maica.auth.models import User
from maica.evidence import aggregates, repository
from maica.evidence import shortlist as shortlist_queries
from maica.reasoning.phrasing import describe_reason
from maica.web.flash import set_flash
from maica.web.nav import SESSION_KEY
from maica.web.report_pdf import AnalysisReport, SourceSummary, build_analysis_pdf

router = APIRouter()


def _safe_filename(name: str | None, fallback: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in (name or "")).strip("-")
    return cleaned.lower() or fallback


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/export")
async def export_analysis(
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """The analysis as a PDF a consultant can hand to a client.

    It used to be a JSON dump of every stored row, which is an archive rather
    than a document — nobody reads 50,000 rows of JSON to find out what
    happened. This carries what was uploaded, what it covers, what could not
    be checked, and the records worth opening.
    """
    analysis = await repository.get_analysis(session, tenant_id, analysis_id)
    if analysis is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    tenant = await repository.get_tenant(session, tenant_id)
    totals = await aggregates.get_analysis_totals(session, tenant_id, analysis_id)
    shortlist = await shortlist_queries.get_shortlist(
        session,
        tenant_id,
        analysis_id,
        total_records=totals.records,
        has_change_evidence=totals.records_with_change_evidence > 0,
        unattributed_rows=totals.unattributed_change_rows,
    )
    raw_evidence = await repository.get_raw_evidence_for_analysis(session, tenant_id, analysis_id)

    report = AnalysisReport(
        tenant_name=tenant.name if tenant else "Client account",
        analysis_id=str(analysis_id),
        total_records=totals.records,
        records_with_change_evidence=totals.records_with_change_evidence,
        sources=[
            SourceSummary(
                source_type=item.source_type,
                rows_understood=item.understood_summary.get("rows_understood", 0),
                rows_skipped=item.understood_summary.get("rows_skipped", 0),
                columns_ignored=list(item.understood_summary.get("columns_ignored", [])),
            )
            for item in raw_evidence
        ],
        shortlist=[
            (
                entry.source_id,
                entry.record_type,
                describe_reason(entry.reasons[0]) if entry.reasons else "",
            )
            for entry in shortlist.entries
        ],
        ranked_on=(
            "Ranked on which field values each record holds — this analysis carries no "
            "change history."
            if shortlist.key_kind == "value"
            else "Ranked on how unusual each record's changes are for this account."
        ),
    )

    name = _safe_filename(tenant.name if tenant else None, "client-account")
    return Response(
        content=build_analysis_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="maica-{name}-analysis.pdf"'},
    )


@router.post("/tenants/{tenant_id}/delete")
async def delete_client_account(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    await repository.delete_tenant_data(session, tenant_id)
    await auth_repository.delete_tenant(session, tenant_id)
    await session.commit()

    # The sidebar remembers the last account, analysis and record opened. Left
    # alone it would keep offering links into an account that no longer exists.
    if (request.session.get(SESSION_KEY) or {}).get("tenant_id") == str(tenant_id):
        request.session.pop(SESSION_KEY, None)

    set_flash(request, "Client account deleted successfully")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/tenants/{tenant_id}/analyses/{analysis_id}/delete")
async def delete_analysis(
    request: Request,
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    await repository.delete_analysis(session, tenant_id, analysis_id)
    await session.commit()

    stored = request.session.get(SESSION_KEY) or {}
    if stored.get("analysis_id") == str(analysis_id):
        stored["analysis_id"] = None
        stored["source_id"] = None
        request.session[SESSION_KEY] = stored

    set_flash(request, "Analysis deleted successfully")
    return RedirectResponse(
        url=f"/tenants/{tenant_id}/analyses", status_code=status.HTTP_303_SEE_OTHER
    )
