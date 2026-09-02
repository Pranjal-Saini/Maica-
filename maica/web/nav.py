"""The sidebar navigation model.

Every page shares one sidebar, but most of its destinations only exist once
the consultant has picked a client account, then an analysis, then a record.
Rather than render dead links, an item without enough context comes back
disabled with a plain reason — the same "say what is missing" posture the
reports themselves take.
"""

import uuid
from dataclasses import dataclass

from maica.auth.models import User

NEEDS_TENANT = "Open a client account first"
NEEDS_ANALYSIS = "Open an analysis first"
NEEDS_RECORD = "Open a record first"


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    href: str | None = None
    badge: str | None = None
    disabled_reason: str | None = None

    @property
    def is_enabled(self) -> bool:
        return self.href is not None


def build_nav(
    *,
    tenant_id: uuid.UUID | None = None,
    analysis_id: uuid.UUID | None = None,
    source_id: str | None = None,
    tenant_count: int | None = None,
) -> list[NavItem]:
    tenant_base = f"/tenants/{tenant_id}" if tenant_id else None
    analysis_base = f"{tenant_base}/analyses/{analysis_id}" if tenant_base and analysis_id else None

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
            href=f"{tenant_base}/analyses" if tenant_base else None,
            disabled_reason=None if tenant_base else NEEDS_TENANT,
        ),
        NavItem(
            key="evidence",
            label="Evidence & chat",
            icon="upload",
            href=f"{tenant_base}/uploads/new" if tenant_base else None,
            disabled_reason=None if tenant_base else NEEDS_TENANT,
        ),
        NavItem(
            key="deep_dive",
            label="Deep dive",
            icon="deepdive",
            href=f"{analysis_base}/records" if analysis_base else None,
            disabled_reason=None if analysis_base else NEEDS_ANALYSIS,
        ),
        NavItem(
            key="factors",
            label="Ranked factors",
            icon="factors",
            href=f"{analysis_base}/records/{source_id}/report"
            if analysis_base and source_id
            else None,
            disabled_reason=None if (analysis_base and source_id) else NEEDS_RECORD,
        ),
    ]


def page_context(
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
    return {
        "user": user,
        "nav_active": active,
        "nav_items": build_nav(
            tenant_id=tenant_id,
            analysis_id=analysis_id,
            source_id=source_id,
            tenant_count=tenant_count,
        ),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "analysis_id": analysis_id,
        "source_id": source_id,
    }
