from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maica.auth.models import User
from maica.config.settings import get_settings
from tests.conftest import create_tenant, login_as, logout, signup_with_tenant


@pytest.fixture
def google_configured(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Scopes a fake Google client id/secret to one test, then releases the
    cached Settings singleton so later tests re-read the environment."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def google_not_configured(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Forces the unconfigured state explicitly. Without this these tests would
    silently depend on the developer's own .env having no Google credentials —
    which broke the moment real ones were added locally."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _extract_state(redirect_location: str) -> str:
    query = parse_qs(urlparse(redirect_location).query)
    return query["state"][0]


def _mock_google_endpoints(*, sub: str, email: str, name: str | None = "Test User") -> None:
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "fake-access-token"})
    )
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=httpx.Response(
            200, json={"sub": sub, "email": email, "email_verified": True, "name": name}
        )
    )


async def test_dashboard_requires_login(client: AsyncClient) -> None:
    response = await client.get("/dashboard")
    assert response.status_code == 401


async def test_root_redirects_anonymous_visitor_to_login(client: AsyncClient) -> None:
    # Regression: "/" used to 404, which is what a first-time visitor typing
    # the bare host would hit.
    response = await client.get("/")

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@respx.mock
async def test_root_redirects_signed_in_user_to_dashboard(
    client: AsyncClient, google_configured: None
) -> None:
    _mock_google_endpoints(sub="google-sub-root", email="consultant@example.com")
    login_response = await client.get("/auth/google/login")
    state = _extract_state(login_response.headers["location"])
    await client.get("/auth/google/callback", params={"code": "fake-code", "state": state})

    response = await client.get("/")

    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


async def test_login_page_hides_google_button_when_not_configured(
    client: AsyncClient, google_not_configured: None
) -> None:
    response = await client.get("/login")

    assert response.status_code == 200
    assert "Continue with Google" not in response.text
    assert "not configured" in response.text


async def test_login_page_shows_google_button_when_configured(
    client: AsyncClient, google_configured: None
) -> None:
    response = await client.get("/login")

    assert response.status_code == 200
    assert "Continue with Google" in response.text


async def test_google_login_redirects_to_google_with_state(
    client: AsyncClient, google_configured: None
) -> None:
    response = await client.get("/auth/google/login")

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "state=" in location


async def test_google_login_shows_error_when_not_configured(
    client: AsyncClient, google_not_configured: None
) -> None:
    response = await client.get("/auth/google/login")

    assert response.status_code == 503
    assert "not configured" in response.text


@respx.mock
async def test_google_callback_creates_new_user_and_logs_in(
    client: AsyncClient, db_session: AsyncSession, google_configured: None
) -> None:
    _mock_google_endpoints(sub="google-sub-1", email="consultant@example.com")

    login_response = await client.get("/auth/google/login")
    state = _extract_state(login_response.headers["location"])

    callback_response = await client.get(
        "/auth/google/callback", params={"code": "fake-code", "state": state}
    )

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == "/dashboard"

    result = await db_session.execute(select(User).where(User.google_sub == "google-sub-1"))
    user = result.scalar_one()
    assert user.email == "consultant@example.com"

    dashboard_response = await client.get("/dashboard")
    assert dashboard_response.status_code == 200
    assert (
        "consultant@example.com" in dashboard_response.text
        or "Test User" in dashboard_response.text
    )


@respx.mock
async def test_google_callback_matches_existing_user_by_google_sub(
    client: AsyncClient, db_session: AsyncSession, google_configured: None
) -> None:
    _mock_google_endpoints(sub="google-sub-2", email="consultant@example.com")

    for _ in range(2):
        login_response = await client.get("/auth/google/login")
        state = _extract_state(login_response.headers["location"])
        await client.get("/auth/google/callback", params={"code": "fake-code", "state": state})

    result = await db_session.execute(select(User).where(User.google_sub == "google-sub-2"))
    users = result.scalars().all()
    assert len(users) == 1


async def test_google_callback_rejects_state_mismatch(
    client: AsyncClient, google_configured: None
) -> None:
    await client.get("/auth/google/login")  # stores the real state in session

    response = await client.get(
        "/auth/google/callback", params={"code": "fake-code", "state": "tampered-state"}
    )

    assert response.status_code == 400
    assert "could not be verified" in response.text


async def test_google_callback_handles_denied_access(
    client: AsyncClient, google_configured: None
) -> None:
    response = await client.get("/auth/google/callback", params={"error": "access_denied"})

    assert response.status_code == 400
    assert "cancelled or denied" in response.text


async def test_creating_tenant_grants_access_and_appears_on_dashboard(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "Acme Corp" in response.text
    assert f"/tenants/{tenant_id}/analyses" in response.text


async def test_one_user_can_access_multiple_tenants(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await login_as(client, db_session, "consultant@example.com")
    first_tenant_id = await create_tenant(client, "Acme Corp")
    second_tenant_id = await create_tenant(client, "Beta LLC")

    response = await client.get("/dashboard")

    assert "Acme Corp" in response.text
    assert "Beta LLC" in response.text

    first_analyses = await client.get(f"/tenants/{first_tenant_id}/analyses")
    second_analyses = await client.get(f"/tenants/{second_tenant_id}/analyses")
    assert first_analyses.status_code == 200
    assert second_analyses.status_code == 200


async def test_user_cannot_access_another_users_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(
        client, db_session, "consultant-a@example.com", "Acme Corp"
    )
    await logout(client)
    await login_as(client, db_session, "consultant-b@example.com")

    response = await client.get(f"/tenants/{tenant_id}/analyses")

    assert response.status_code == 403
