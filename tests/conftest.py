import os
from collections.abc import AsyncGenerator

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://maica:maica@localhost:5432/maica_test")

import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from maica.api.deps import get_current_user, get_db_session, get_llm_client
from maica.api.main import create_app
from maica.auth import repository as auth_repository
from maica.auth.models import User, UserTenantAccess
from maica.config.settings import get_settings
from maica.evidence.db import Base
from maica.evidence.models import Analysis, RawEvidence, Record, Tenant
from maica.web.csrf import HEADER_FIELD


@pytest.fixture(scope="session")
async def _schema() -> AsyncGenerator[None, None]:
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
async def db_session(_schema: None) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(get_settings().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.execute(delete(Record))
        await session.execute(delete(RawEvidence))
        await session.execute(delete(Analysis))
        await session.execute(delete(UserTenantAccess))
        await session.execute(delete(User))
        await session.execute(delete(Tenant))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    async def _override_get_llm_client() -> None:
        # Integration tests never depend on a real, running LLM — the LLM
        # layer itself is covered by tests/unit/test_llm_explanation.py and
        # tests/unit/test_ollama_client.py with fake/mocked clients. This
        # keeps the suite fast and deterministic regardless of whether
        # Ollama happens to be running on the machine.
        return None

    app.dependency_overrides[get_llm_client] = _override_get_llm_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.app_for_tests = app  # type: ignore[attr-defined]  # see login_as() below
        yield ac


async def login_as(client: AsyncClient, db_session: AsyncSession, email: str) -> User:
    """Test-only shortcut that bypasses the real Google OAuth redirect flow:
    creates (or reuses) a user directly and overrides get_current_user so
    every subsequent request on this client is authenticated as them. Real
    Google Sign-In itself (state CSRF check, code exchange, user
    creation/matching) is covered separately in test_auth.py against mocked
    Google endpoints — most tests don't care how the user got authenticated,
    only what they can/can't then do."""
    user = await auth_repository.get_user_by_email(db_session, email)
    if user is None:
        user = await auth_repository.create_user(
            db_session, google_sub=f"test-sub:{email}", email=email, name=None
        )
        await db_session.commit()

    async def _override_get_current_user() -> User:
        return user

    client.app_for_tests.dependency_overrides[get_current_user] = _override_get_current_user  # type: ignore[attr-defined]
    await arm_csrf(client)
    return user


async def arm_csrf(client: AsyncClient) -> str:
    """Reads the session's CSRF token from a rendered form and sends it on
    every later request, which is what a browser does with the hidden field.

    Armed here rather than at each call site so that a route gaining
    verify_csrf() does not silently break tests that are about something else.
    Tests that exercise the CSRF control itself strip this header first — see
    test_security.py — so "no token" stays something a test has to ask for.
    """
    page = await client.get("/tenants/new")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match is not None, "no CSRF token rendered on /tenants/new"
    token = match.group(1)
    client.headers[HEADER_FIELD] = token
    return token


async def logout(client: AsyncClient) -> None:
    client.app_for_tests.dependency_overrides.pop(get_current_user, None)  # type: ignore[attr-defined]


async def create_tenant(client: AsyncClient, name: str) -> str:
    """Creates a client-account workspace under the currently logged-in user
    and returns its tenant_id."""
    response = await client.post("/tenants", data={"name": name})
    assert response.status_code == 303, response.text
    location = response.headers["location"]  # "/tenants/{tenant_id}/analyses"
    return location.split("/")[2]


async def signup_with_tenant(
    client: AsyncClient, db_session: AsyncSession, email: str, tenant_name: str
) -> str:
    await login_as(client, db_session, email)
    return await create_tenant(client, tenant_name)
