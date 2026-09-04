"""The way into an analysis: which transaction posted wrong?

The product's promise is one sentence — when a transaction posts wrong, read
the account and return a ranked map of contributing factors. The consultant
almost always arrives holding that transaction, so this page asks for it and
gets out of the way.

It used to also carry a pattern index of every change signature in the
account. That answered "what does this account do", which nobody asked
mid-investigation, and on a real account it put several hundred things on
screen next to the eight that mattered. It is gone.

The record shortlist survives underneath, for the consultant who genuinely has
no transaction to start from. It is the weaker path and is presented as one.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_current_user, get_db_session
from maica.auth.models import User
from maica.evidence import aggregates
from maica.evidence import repository as evidence_repository
from maica.evidence import shortlist as shortlist_queries
from maica.reasoning.phrasing import describe_reason
from maica.web.nav import page_context
from maica.web.templating import templates

router = APIRouter()


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/records", response_model=None)
async def deep_dive(
    request: Request,
    analysis_id: uuid.UUID,
    q: str = Query(""),
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    """Takes a transaction and hands straight over to its ranked factors."""
    asked = q.strip()
    if asked and await aggregates.source_id_exists(session, tenant_id, analysis_id, asked):
        return RedirectResponse(
            url=f"/tenants/{tenant_id}/analyses/{analysis_id}/records/{asked}/report",
            status_code=303,
        )

    totals = await aggregates.get_analysis_totals(session, tenant_id, analysis_id)
    shortlist = await shortlist_queries.get_shortlist(
        session,
        tenant_id,
        analysis_id,
        total_records=totals.records,
        has_change_evidence=totals.records_with_change_evidence > 0,
        unattributed_rows=totals.unattributed_change_rows,
    )
    tenant = await evidence_repository.get_tenant(session, tenant_id)

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
        | {
            "shortlist": shortlist,
            "describe_reason": describe_reason,
            "not_found": asked if asked else None,
            "total_records": totals.records,
        },
    )
