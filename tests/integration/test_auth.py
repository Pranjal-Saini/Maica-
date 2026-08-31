from httpx import AsyncClient

from tests.conftest import DEFAULT_PASSWORD, create_tenant, signup, signup_with_tenant


async def test_signup_then_dashboard_shows_no_tenants(client: AsyncClient) -> None:
    await signup(client, "consultant@example.com")

    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "consultant@example.com" in response.text
    assert "No client accounts yet" in response.text


async def test_signup_with_duplicate_email_is_rejected(client: AsyncClient) -> None:
    await signup(client, "consultant@example.com")
    await client.post("/logout")

    response = await client.post(
        "/signup", data={"email": "consultant@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 400
    assert "already exists" in response.text


async def test_login_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    await signup(client, "consultant@example.com")
    await client.post("/logout")

    response = await client.post(
        "/login", data={"email": "consultant@example.com", "password": "wrong password"}
    )

    assert response.status_code == 400
    assert "Incorrect email or password" in response.text


async def test_login_with_correct_password_succeeds(client: AsyncClient) -> None:
    await signup(client, "consultant@example.com")
    await client.post("/logout")

    response = await client.post(
        "/login", data={"email": "consultant@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


async def test_logout_then_dashboard_requires_login(client: AsyncClient) -> None:
    await signup(client, "consultant@example.com")
    await client.post("/logout")

    response = await client.get("/dashboard")

    assert response.status_code == 401


async def test_dashboard_requires_login(client: AsyncClient) -> None:
    response = await client.get("/dashboard")
    assert response.status_code == 401


async def test_creating_tenant_grants_access_and_appears_on_dashboard(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")

    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "Acme Corp" in response.text
    assert f"/tenants/{tenant_id}/analyses" in response.text


async def test_one_user_can_access_multiple_tenants(client: AsyncClient) -> None:
    await signup(client, "consultant@example.com")
    first_tenant_id = await create_tenant(client, "Acme Corp")
    second_tenant_id = await create_tenant(client, "Beta LLC")

    response = await client.get("/dashboard")

    assert "Acme Corp" in response.text
    assert "Beta LLC" in response.text

    first_analyses = await client.get(f"/tenants/{first_tenant_id}/analyses")
    second_analyses = await client.get(f"/tenants/{second_tenant_id}/analyses")
    assert first_analyses.status_code == 200
    assert second_analyses.status_code == 200


async def test_user_cannot_access_another_users_tenant(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant-a@example.com", "Acme Corp")
    await client.post("/logout")
    await signup(client, "consultant-b@example.com")

    response = await client.get(f"/tenants/{tenant_id}/analyses")

    assert response.status_code == 403
