"""The shared sidebar shell: every signed-in page renders it, and its
tenant-scoped destinations only unlock once the context exists."""

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from maica.web.nav import NEEDS_TENANT
from tests.conftest import create_tenant, login_as, signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def _upload_fixture(client: AsyncClient, tenant_id: str) -> str:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    return response.json()["analysis_id"]


async def test_dashboard_locks_tenant_scoped_nav_until_an_account_is_open(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.get("/dashboard")

    assert "Client accounts" in response.text
    assert "Deep dive" in response.text
    # Rendered, but as a disabled row explaining what is missing.
    assert NEEDS_TENANT in response.text


async def test_report_page_unlocks_every_sidebar_destination(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    text = response.text
    assert f"/tenants/{tenant_id}/uploads/new" in text
    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/records" in text
    assert NEEDS_TENANT not in text


async def test_report_page_carries_the_chat_panel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The chat used to live only on the upload page, where there is nothing to
    # discuss yet. It belongs where the ranked factors are.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    assert 'id="chat-panel"' in response.text
    assert f'data-analysis-id="{analysis_id}"' in response.text


async def test_upload_page_renders_with_chat_disabled_before_any_analysis(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.get(f"/tenants/{tenant_id}/uploads/new")

    assert response.status_code == 200
    assert 'data-analysis-id=""' in response.text
    assert "Upload evidence first" in response.text


async def test_client_account_cards_show_analysis_activity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    quiet_tenant_id = await create_tenant(client, "Beta LLC")
    await _upload_fixture(client, str(tenant_id))

    response = await client.get("/dashboard")

    text = response.text
    assert "1 analysis" in text
    assert "No analyses yet" in text
    assert f"/tenants/{tenant_id}/analyses" in text
    assert f"/tenants/{quiet_tenant_id}/analyses" in text


async def test_dashboard_with_no_accounts_still_renders_the_shell(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await login_as(client, db_session, "consultant@example.com")

    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "Add a client account" in response.text
    assert "No client accounts yet" in response.text
