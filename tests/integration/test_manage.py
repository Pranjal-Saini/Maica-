"""Exporting and deleting what MAICA stores.

These are the only routes that remove data, so tenant isolation matters more
here than anywhere else: a delete that crossed accounts would destroy another
consultant's evidence.
"""

import json
import uuid
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.models import Analysis, RawEvidence, Record, Tenant
from tests.conftest import create_tenant, login_as, logout, signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def _upload(client: AsyncClient, tenant_id: str) -> str:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    return response.json()["analysis_id"]


async def test_export_client_account_carries_records_and_the_uploaded_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    await _upload(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    bundle = json.loads(response.text)
    assert bundle["tenant_name"] == "Acme Corp"
    assert len(bundle["analyses"]) == 1
    analysis = bundle["analyses"][0]
    assert any(r["source_id"] == "1001" for r in analysis["records"])
    # The original rows travel too — a normalized-only export cannot be
    # audited back against NetSuite.
    assert analysis["raw_evidence"][0]["payload"]["rows"]


async def test_export_one_analysis(client: AsyncClient, db_session: AsyncSession) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/export")

    assert response.status_code == 200
    bundle = json.loads(response.text)
    assert [a["analysis_id"] for a in bundle["analyses"]] == [analysis_id]


async def test_deleting_an_analysis_removes_its_evidence_and_records(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.post(f"/tenants/{tenant_id}/analyses/{analysis_id}/delete")

    assert response.status_code == 303
    assert response.headers["location"] == f"/tenants/{tenant_id}/analyses"
    assert (await db_session.execute(select(Analysis))).scalars().all() == []
    assert (await db_session.execute(select(RawEvidence))).scalars().all() == []
    assert (await db_session.execute(select(Record))).scalars().all() == []
    # The client account itself survives.
    assert (await db_session.execute(select(Tenant))).scalars().one().name == "Acme Corp"


async def test_deleting_a_client_account_removes_everything_under_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    await _upload(client, str(tenant_id))

    response = await client.post(f"/tenants/{tenant_id}/delete")

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert (await db_session.execute(select(Tenant))).scalars().all() == []
    assert (await db_session.execute(select(Analysis))).scalars().all() == []
    assert (await db_session.execute(select(Record))).scalars().all() == []
    assert "Acme Corp" not in (await client.get("/dashboard")).text


async def test_deleting_one_account_leaves_another_untouched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    doomed = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    kept = await create_tenant(client, "Beta LLC")
    await _upload(client, str(doomed))
    kept_analysis = await _upload(client, str(kept))

    await client.post(f"/tenants/{doomed}/delete")

    remaining = (await db_session.execute(select(Analysis))).scalars().all()
    assert [str(a.id) for a in remaining] == [kept_analysis]
    assert "Beta LLC" in (await client.get("/dashboard")).text


async def test_another_users_account_can_be_neither_exported_nor_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(
        client, db_session, "consultant-a@example.com", "Acme Corp"
    )
    analysis_id = await _upload(client, str(tenant_id))
    await logout(client)
    await login_as(client, db_session, "consultant-b@example.com")

    assert (await client.get(f"/tenants/{tenant_id}/export")).status_code == 403
    assert (await client.post(f"/tenants/{tenant_id}/delete")).status_code == 403
    assert (
        await client.post(f"/tenants/{tenant_id}/analyses/{analysis_id}/delete")
    ).status_code == 403

    # Nothing was touched by the attempts.
    assert (await db_session.execute(select(Tenant))).scalars().one().name == "Acme Corp"
    assert len((await db_session.execute(select(Analysis))).scalars().all()) == 1


async def test_deleting_the_open_account_clears_the_remembered_sidebar_context(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The sidebar remembers the last account opened. Left alone it would keep
    # linking into an account that no longer exists.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))
    await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    await client.post(f"/tenants/{tenant_id}/delete")

    assert str(tenant_id) not in (await client.get("/dashboard")).text


async def test_exporting_an_analysis_that_does_not_exist_is_a_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.get(f"/tenants/{tenant_id}/analyses/{uuid.uuid4()}/export")

    assert response.status_code == 404


async def test_deleting_shows_a_confirmation_message_on_the_next_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    await create_tenant(client, "Beta LLC")

    await client.post(f"/tenants/{tenant_id}/delete")
    dashboard = await client.get("/dashboard")

    assert "Client account deleted successfully" in dashboard.text
    assert 'id="toast"' in dashboard.text


async def test_deleting_an_analysis_reports_it_on_the_analyses_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    await client.post(f"/tenants/{tenant_id}/analyses/{analysis_id}/delete")
    page = await client.get(f"/tenants/{tenant_id}/analyses")

    assert "Analysis deleted successfully" in page.text


async def test_the_message_does_not_survive_a_refresh(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Otherwise every later page view claims something was just deleted.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    await create_tenant(client, "Beta LLC")

    await client.post(f"/tenants/{tenant_id}/delete")
    first = await client.get("/dashboard")
    second = await client.get("/dashboard")

    assert "deleted successfully" in first.text
    assert "deleted successfully" not in second.text
