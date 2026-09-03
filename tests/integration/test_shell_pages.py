"""The shared sidebar shell: every signed-in page renders it, every row in
it is clickable, and the rows remember the last place the consultant was."""

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from maica.web.nav import NEED_ACCOUNT, NEED_ANALYSIS, NEED_PROMPTS
from tests.conftest import create_tenant, login_as, logout, signup_with_tenant

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


async def test_report_page_does_not_wait_on_the_language_model(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The report is deterministic; only its wording comes from the model. It
    # used to block on one model call per factor, which made the page feel
    # broken. The rule-based summary must be in the first response, with the
    # narration fetched afterwards.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    text = response.text
    assert "UNCERTAIN" in text
    assert "Correlation only:" in text  # the rule-based wording, not the model's
    assert "records/1001/explain" in text  # narration is fetched, not awaited


async def test_chat_window_opens_as_its_own_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/chat")

    assert response.status_code == 200
    # Its own window: no sidebar shell around it.
    assert 'id="sidebar"' not in response.text
    assert "Ask about this evidence" in response.text
    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/chat" in response.text


async def test_chat_window_is_tenant_guarded(client: AsyncClient, db_session: AsyncSession) -> None:
    tenant_id = await signup_with_tenant(
        client, db_session, "consultant-a@example.com", "Acme Corp"
    )
    analysis_id = await _upload_fixture(client, str(tenant_id))
    await logout(client)
    await login_as(client, db_session, "consultant-b@example.com")

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/chat")

    assert response.status_code == 403


async def test_chat_opens_as_a_full_tab_not_a_sized_popup(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # window.open with a feature string makes a small popup; without one the
    # browser opens a normal tab, which is what a full-width chat needs.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    assert 'window.open(url, "maica-chat")' in response.text
    assert "width=460" not in response.text


async def test_report_shows_the_rows_behind_each_factor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The trust problem: a bare "Supporting records: 4471" asks the consultant
    # to take the ranking on faith. The actual field, values, actor, context
    # and timestamp have to be on the page so they can check it in NetSuite.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    notes = (
        b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Context,Type\n"
        b"4471,Invoice,7/12/2026 09:15,Account,4000 - Product Revenue,"
        b"4010 - Service Revenue,System,SCHEDULED,Change\n"
    )
    analysis_id = (
        await client.post(
            f"/tenants/{tenant_id}/uploads",
            files={"files": ("notes.csv", notes, "text/csv")},
        )
    ).json()["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/4471/report")

    text = response.text
    assert "Evidence — check these rows in NetSuite" in text
    assert "4000 - Product Revenue" in text
    assert "4010 - Service Revenue" in text
    assert "SCHEDULED" in text
    assert "12 Jul 2026 09:15" in text


async def test_report_states_that_confirmed_means_the_change_not_the_cause(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    notes = (
        b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Context,Type\n"
        b"4471,Invoice,7/12/2026 09:15,Account,4000,4010,System,SCHEDULED,Change\n"
    )
    analysis_id = (
        await client.post(
            f"/tenants/{tenant_id}/uploads",
            files={"files": ("notes.csv", notes, "text/csv")},
        )
    ).json()["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/4471/report")

    text = response.text
    assert "CONFIRMED" in text
    assert "never that it" in text and "caused the outcome" in text
    assert "What the labels mean" in text


async def test_chat_analyses_the_record_on_screen_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # On a real account the bundle can only hold a handful of records. Without
    # a focus it holds whichever sort first alphabetically — never the one the
    # consultant is looking at.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    analysis_id = (
        await client.post(
            f"/tenants/{tenant_id}/uploads",
            files={"files": ("s.csv", csv_bytes, "text/csv")},
        )
    ).json()["analysis_id"]

    response = await client.post(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/chat",
        json={"question": "what changed?", "history": [], "focus_source_id": "1003"},
    )

    assert response.status_code == 200


async def test_report_chat_link_carries_the_record_being_viewed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload_fixture(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    assert 'data-source-id="1001"' in response.text


async def test_logo_is_served_and_used_instead_of_the_letter_tile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await login_as(client, db_session, "consultant@example.com")

    page = await client.get("/dashboard")
    asset = await client.get("/static/maica-logo.png")

    assert asset.status_code == 200
    assert asset.headers["content-type"] == "image/png"
    assert "/static/maica-logo.png" in page.text
    assert "maica-wordmark" in page.text


async def test_sidebar_stays_put_and_only_the_content_panel_scrolls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The shell used to be min-h-screen, so a long report grew the sidebar with
    # it and scrolled the nav — and the read-only card — off the screen.
    await login_as(client, db_session, "consultant@example.com")

    text = (await client.get("/dashboard")).text

    assert "flex h-screen gap-3 overflow-hidden" in text
    assert 'id="main-panel"' in text
    assert "overflow-y-auto rounded-[26px] bg-white" in text


async def test_read_only_note_sits_at_the_foot_of_the_sidebar(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # mt-auto only puts it on screen because the sidebar is the viewport's
    # height now. Back when the shell was min-h-screen it pushed the note to
    # the bottom of the whole document, which is why it was never visible.
    await login_as(client, db_session, "consultant@example.com")

    text = (await client.get("/dashboard")).text
    aside = text[text.index("<aside") : text.index("</aside>")]

    assert "never writes to a client NetSuite account" in aside
    assert 'class="side-label mt-auto' in aside
    assert aside.index("side-label mt-auto") > aside.index("</nav>")
