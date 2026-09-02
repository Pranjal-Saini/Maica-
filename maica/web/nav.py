"""The sidebar navigation model.

Every page shares one sidebar, and every row in it is clickable. Most rows
need a client account, then an analysis, then a record before they point at
real data — so the shell remembers the last one the consultant actually
opened and reuses it. When there is genuinely nothing to remember, the row
still leads somewhere useful: the page where that context gets picked,
carrying a `need` hint so it can say what to choose.
"""

import uuid
from dataclasses import dataclass

from starlette.requests import Request

from maica.auth.models import User

SESSION_KEY = "nav_context"

NEED_ACCOUNT = "account"
NEED_ANALYSIS = "analysis"
NEED_RECORD = "record"

NEED_PROMPTS = {
    NEED_ACCOUNT: "Open a client account first — analyses, evidence and reports live inside one.",
    NEED_ANALYSIS: "Open an analysis first — its records and ranked factors live inside it.",
    NEED_RECORD: "Open a record to see its ranked contributing factors.",
}


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    href: str
    badge: str | None = None
    #: Set when the row leads to a picker instead of the section itself.
    needs: str | None = None


@dataclass(frozen=True)
class NavContext:
    """The last place the consultant actually was."""

    tenant_id: str | None = None
    analysis_id: str | None = None
    source_id: str | None = None


def remember_context(
    request: Request,
    *,
    tenant_id: uuid.UUID | None = None,
    analysis_id: uuid.UUID | None = None,
    source_id: str | None = None,
) -> NavContext:
    """Stores this page's context in the session and returns the merged view.

    Narrowing resets what sits below it: moving to a different client account
    drops the remembered analysis and record, because they belong to the
    account being left. Without that the sidebar would happily link one
    tenant's analysis from another tenant's page.
    """
    stored = request.session.get(SESSION_KEY) or {}
    context = NavContext(
        tenant_id=stored.get("tenant_id"),
        analysis_id=stored.get("analysis_id"),
        source_id=stored.get("source_id"),
    )

    if tenant_id is not None and str(tenant_id) != context.tenant_id:
        context = NavContext(tenant_id=str(tenant_id))
    if analysis_id is not None and str(analysis_id) != context.analysis_id:
        context = NavContext(tenant_id=context.tenant_id, analysis_id=str(analysis_id))
    if source_id is not None:
        context = NavContext(
            tenant_id=context.tenant_id,
            analysis_id=context.analysis_id,
            source_id=source_id,
        )

    request.session[SESSION_KEY] = {
        "tenant_id": context.tenant_id,
        "analysis_id": context.analysis_id,
        "source_id": context.source_id,
    }
    return context


def build_nav(context: NavContext, *, tenant_count: int | None = None) -> list[NavItem]:
    tenant = context.tenant_id
    analysis = context.analysis_id if tenant else None
    source = context.source_id if analysis else None

    pick_account = f"/dashboard?need={NEED_ACCOUNT}"
    pick_analysis = f"/tenants/{tenant}/analyses?need={NEED_ANALYSIS}" if tenant else pick_account
    pick_record = (
        f"/tenants/{tenant}/analyses/{analysis}/records?need={NEED_RECORD}"
        if analysis
        else pick_analysis
    )

    return [
        NavItem(
            key="accounts",
            label="Client accounts",
            icon="accounts",
            href="/dashboard",
            badge=str(tenant_count) if tenant_count else None,
        ),
        NavItem(
            key="analyses",
            label="Analyses",
            icon="analyses",
            href=f"/tenants/{tenant}/analyses" if tenant else pick_account,
            needs=None if tenant else NEED_ACCOUNT,
        ),
        NavItem(
            key="evidence",
            label="Evidence & chat",
            icon="upload",
            href=f"/tenants/{tenant}/uploads/new" if tenant else pick_account,
            needs=None if tenant else NEED_ACCOUNT,
        ),
        NavItem(
            key="deep_dive",
            label="Deep dive",
            icon="deepdive",
            href=f"/tenants/{tenant}/analyses/{analysis}/records" if analysis else pick_analysis,
            needs=None if analysis else (NEED_ANALYSIS if tenant else NEED_ACCOUNT),
        ),
        NavItem(
            key="factors",
            label="Ranked factors",
            icon="factors",
            href=f"/tenants/{tenant}/analyses/{analysis}/records/{source}/report"
            if source
            else pick_record,
            needs=None
            if source
            else (NEED_RECORD if analysis else (NEED_ANALYSIS if tenant else NEED_ACCOUNT)),
        ),
    ]


def page_context(
    request: Request,
    *,
    user: User,
    active: str,
    tenant_id: uuid.UUID | None = None,
    tenant_name: str | None = None,
    analysis_id: uuid.UUID | None = None,
    source_id: str | None = None,
    tenant_count: int | None = None,
) -> dict:
    """The shell context every page built on base.html needs. Routes merge
    their own page data on top of this."""
    context = remember_context(
        request, tenant_id=tenant_id, analysis_id=analysis_id, source_id=source_id
    )
    need = request.query_params.get("need")
    return {
        "user": user,
        "nav_active": active,
        "nav_items": build_nav(context, tenant_count=tenant_count),
        "need_prompt": NEED_PROMPTS.get(need) if need else None,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "analysis_id": analysis_id,
        "source_id": source_id,
    }
