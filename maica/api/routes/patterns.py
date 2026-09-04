"""The deep dive: what happened across an analysis, rather than every record.

Listing 10,000 records sorted by ID asks the consultant to already know the
answer. These routes group the same evidence into a few dozen patterns and let
them drill from one into the records behind it.

Route handlers here only wire things together — the counting is in
evidence/aggregates.py and the grouping in reasoning/patterns.py, per
conventions.md.
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
from maica.reasoning.patterns import (
    RECORDS_PER_PAGE,
    SORT_LARGEST,
    ChangePattern,
    build_pattern_index,
    describe_reason,
    value_facets,
)
from maica.web.nav import page_context
from maica.web.templating import templates

router = APIRouter()


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/records", response_model=None)
async def deep_dive(
    request: Request,
    analysis_id: uuid.UUID,
    sort: str = Query(SORT_LARGEST),
    q: str = Query(""),
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    """The pattern index.

    Everything here is a grouped count, so the work does not grow with the
    number of records — which is the whole point, and why this route must never
    call diagnose().
    """
    jumped = q.strip()
    if jumped and await aggregates.source_id_exists(session, tenant_id, analysis_id, jumped):
        return RedirectResponse(
            url=f"/tenants/{tenant_id}/analyses/{analysis_id}/records/{jumped}/report",
            status_code=303,
        )

    totals = await aggregates.get_analysis_totals(session, tenant_id, analysis_id)
    total_records = totals.records
    with_changes = totals.records_with_change_evidence
    # The answer to "where do I look" — a handful of records, ranked across the
    # whole analysis. Everything below it is the supporting detail.
    shortlist = await shortlist_queries.get_shortlist(
        session,
        tenant_id,
        analysis_id,
        total_records=total_records,
        has_change_evidence=with_changes > 0,
        unattributed_rows=totals.unattributed_change_rows,
    )

    index = build_pattern_index(
        await aggregates.get_field_totals(session, tenant_id, analysis_id),
        await aggregates.get_change_pattern_rows(session, tenant_id, analysis_id),
        total_records=total_records,
        records_with_change_evidence=with_changes,
        sort=sort,
    )

    # Only worth the extra query when there are no change patterns to show —
    # a saved-search-only analysis, which is Path A's most common first upload.
    facets = (
        value_facets(
            await aggregates.get_value_facet_rows(session, tenant_id, analysis_id),
            total_records=total_records,
        )
        if not index.groups
        else []
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
            "index": index,
            "shortlist": shortlist,
            "describe_reason": describe_reason,
            "facets": facets,
            "jump_miss": jumped if jumped else None,
            "total_records": total_records,
        },
    )


@router.get(
    "/tenants/{tenant_id}/analyses/{analysis_id}/patterns/records", response_class=HTMLResponse
)
async def pattern_records(
    request: Request,
    analysis_id: uuid.UUID,
    field: str = Query(...),
    change_kind: str = Query(...),
    actor_class: str = Query(...),
    context: str | None = Query(None),
    context_missing: int = Query(0),
    page: int = Query(1, ge=1),
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """The records behind one pattern, paged.

    `context` is nullable, so its absence travels as an explicit flag rather
    than a magic string, which would collide with a real context that happened
    to carry the same name.
    """
    resolved_context = None if context_missing else context
    predicate = aggregates.change_pattern_predicate(
        field_name=field,
        change_kind=change_kind,
        actor_class=actor_class,
        context=resolved_context,
    )
    rows, total = await aggregates.get_records_matching(
        session,
        tenant_id,
        analysis_id,
        predicate,
        limit=RECORDS_PER_PAGE,
        offset=(page - 1) * RECORDS_PER_PAGE,
    )

    # Rebuilt for its wording only; the counts on this page come from the query
    # above, so they cannot disagree with the list they head.
    pattern = ChangePattern(
        field_name=field,
        change_kind=change_kind,
        actor_class=actor_class,
        context=resolved_context,
        record_count=total,
        change_count=sum(changes for _, _, changes in rows),
        actors=(),
        first_seen=None,
        last_seen=None,
    )

    tenant = await evidence_repository.get_tenant(session, tenant_id)
    return templates.TemplateResponse(
        request,
        "pattern_records.html",
        page_context(
            request,
            user=user,
            active="deep_dive",
            tenant_id=tenant_id,
            tenant_name=tenant.name if tenant else None,
            analysis_id=analysis_id,
        )
        | {
            "pattern": pattern,
            "records": rows,
            "total": total,
            "page": page,
            "per_page": RECORDS_PER_PAGE,
            "has_next": page * RECORDS_PER_PAGE < total,
            "query": request.url.query,
        },
    )
