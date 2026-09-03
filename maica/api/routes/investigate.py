"""Comparing the records that went wrong against the ones that did not.

The rest of the deep dive answers "what is unusual here", which is the best a
tool can do unprompted. This route asks the consultant the one thing only they
know — which records are actually wrong — and in exchange gives an answer
rather than a list of leads.
"""

import re
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_current_user, get_db_session
from maica.auth.models import User
from maica.evidence import aggregates, contrast
from maica.evidence import repository as evidence_repository
from maica.reasoning.findings import Investigation, investigate
from maica.web.nav import page_context
from maica.web.templating import templates

router = APIRouter()

#: Guards the URL and the IN clause. A consultant pastes a handful to a few
#: hundred IDs from a client's complaint, never thousands.
MAX_PASTED_IDS = 500


def parse_record_ids(raw: str) -> list[str]:
    """Accepts however the consultant had the IDs to hand — commas, spaces,
    newlines, or a column pasted straight out of a spreadsheet."""
    return [token for token in re.split(r"[\s,;]+", raw.strip()) if token][:MAX_PASTED_IDS]


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/investigate", response_class=HTMLResponse)
async def investigate_symptom(
    request: Request,
    analysis_id: uuid.UUID,
    ids: str = Query(""),
    field: str = Query(""),
    value: str = Query(""),
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    record_ids = parse_record_ids(ids)
    described = bool(record_ids or (field and value))

    result: Investigation | None = None
    if described:
        sizes = await contrast.get_cohort_sizes(
            session,
            tenant_id,
            analysis_id,
            record_ids=record_ids or None,
            field_name=field or None,
            value=value or None,
        )
        rows = (
            await contrast.compare_cohorts(
                session,
                tenant_id,
                analysis_id,
                record_ids=record_ids or None,
                field_name=field or None,
                value=value or None,
            )
            if sizes.affected and sizes.rest
            else []
        )
        result = investigate(rows, affected_total=sizes.affected, rest_total=sizes.rest)

    # Offers the fields worth filtering on, so the consultant is not guessing at
    # column names. Cheap: it is the same grouped count the deep dive uses.
    facet_rows = await aggregates.get_value_facet_rows(session, tenant_id, analysis_id)
    tenant = await evidence_repository.get_tenant(session, tenant_id)

    return templates.TemplateResponse(
        request,
        "investigate.html",
        page_context(
            request,
            user=user,
            active="deep_dive",
            tenant_id=tenant_id,
            tenant_name=tenant.name if tenant else None,
            analysis_id=analysis_id,
        )
        | {
            "investigation": result,
            "described": described,
            "ids": ids,
            "field": field,
            "value": value,
            "fields": [row.field_name for row in facet_rows],
        },
    )
