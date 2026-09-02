"""The shared sidebar shell: every signed-in page renders it, every row in
it is clickable, and the rows remember the last place the consultant was."""

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from maica.web.nav import NEED_ACCOUNT, NEED_ANALYSIS, NEED_PROMPTS
from tests.conftest import create_tenant, login_as, signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def _upload_fixture(client: AsyncClient, tenant_id: str) -> str:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    return response.json()["analysis_id"]


async def test_every_sidebar_row_is_clickable_with_no_context_yet(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # A row that needs a client account still leads somewhere — the picker —
    # rather than rendering as a dead control.
    await login_as(client, db_session, "consultant@example.com")

    response = await client.get("/dashboard")

    assert "Client accounts" in response.text
    assert "Deep dive" in response.text
    assert f"/dashboard?need={NEED_ACCOUNT}" in response.text


async def test_picker_page_says_what_to_choose(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await login_as(client, db_session, "consultant@example.com")

    response = await client.get(f"/dashboard?need={NEED_ACCOUNT}")

    assert NEED_PROMPTS[NEED_ACCOUNT] in response.text


async def test_report_page_unlocks_every_sidebar_destination(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    text = response.text
    assert f"/tenants/{tenant_id}/uploads/new" in text
    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/records" in text
    assert f"/dashboard?need={NEED_ACCOUNT}" not in text


async def test_report_page_carries_the_chat_panel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The chat used to live only on the upload page, where there is nothing to
    # discuss yet. It belongs where the ranked factors are.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    assert 'id="chat-dock"' in response.text
    assert f'data-analysis-id="{analysis_id}"' in response.text


async def test_upload_page_renders_with_chat_disabled_before_any_analysis(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.get(f"/tenants/{tenant_id}/uploads/new")

    assert response.status_code == 200
    assert 'data-analysis-id=""' in response.text
    assert "Upload evidence first, then ask about it here" in response.text


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


async def test_sidebar_remembers_the_analysis_after_returning_to_the_dashboard(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The dashboard carries no analysis of its own, but "Deep dive" should
    # still lead back to the one just being worked on.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))
    await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    response = await client.get("/dashboard")

    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report" in response.text


async def test_opening_another_account_forgets_the_previous_analysis(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    other_tenant_id = await create_tenant(client, "Beta LLC")
    analysis_id = await _upload_fixture(client, str(tenant_id))
    await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    response = await client.get(f"/tenants/{other_tenant_id}/analyses")

    # Deep dive must not link into the account that was just left.
    assert str(analysis_id) not in response.text
    assert f"/tenants/{other_tenant_id}/analyses?need={NEED_ANALYSIS}" in response.text
