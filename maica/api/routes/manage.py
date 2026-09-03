"""Exporting and deleting what MAICA holds.

These are the only routes that remove stored data, so they live together
rather than being scattered through the read paths. Client NetSuite access is
untouched by all of them: deleting a client account here removes MAICA's copy
of the evidence and nothing in the ERP, which is worth being able to say
plainly to a client's administrator.

Deletes are POSTs, not DELETEs, because they are driven by plain HTML forms —
the confirmation is native and works without JavaScript.
"""

import json
import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_authorized_tenant_id, get_current_user, get_db_session
from maica.auth import repository as auth_repository
from maica.auth.models import User
from maica.evidence import repository
from maica.web.flash import set_flash
from maica.web.nav import SESSION_KEY

router = APIRouter()


def _json_download(bundle: dict, filename: str) -> Response:
    return Response(
        content=json.dumps(bundle, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe_filename(name: str | None, fallback: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in (name or "")).strip("-")
    return cleaned.lower() or fallback


@router.get("/tenants/{tenant_id}/export")
async def export_client_account(
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    bundle = await repository.export_tenant(session, tenant_id)
    name = _safe_filename(bundle.get("tenant_name"), "client-account")
    return _json_download(bundle, f"maica-{name}.json")


@router.get("/tenants/{tenant_id}/analyses/{analysis_id}/export")
async def export_analysis(
    analysis_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_authorized_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    bundle = await repository.export_analysis(session, tenant_id, analysis_id)
    if bundle is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    name = _safe_filename(bundle.get("tenant_name"), "client-account")
    return _json_download(bundle, f"maica-{name}-{analysis_id}.json")


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
