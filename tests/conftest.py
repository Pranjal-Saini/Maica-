import os
from collections.abc import AsyncGenerator

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://maica:maica@localhost:5432/maica_test")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from maica.api.deps import get_db_session, get_llm_client
from maica.api.main import create_app
from maica.auth.models import (  # noqa: F401 - registers tables on Base.metadata
    User,
    UserTenantAccess,
)
from maica.config.settings import get_settings
from maica.evidence.db import Base
from maica.evidence.models import Analysis, RawEvidence, Record, Tenant

DEFAULT_PASSWORD = "correct horse battery staple"  # noqa: S105 - test fixture only


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
        yield ac


async def signup(client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD) -> None:
    """Signs up and logs in as a fresh user, leaving the session cookie set on
    the given client for subsequent requests."""
    response = await client.post("/signup", data={"email": email, "password": password})
    assert response.status_code == 303, response.text


async def create_tenant(client: AsyncClient, name: str) -> str:
    """Creates a client-account workspace under the currently logged-in user
    and returns its tenant_id."""
    response = await client.post("/tenants", data={"name": name})
    assert response.status_code == 303, response.text
    location = response.headers["location"]  # "/tenants/{tenant_id}/analyses"
    return location.split("/")[2]


async def signup_with_tenant(client: AsyncClient, email: str, tenant_name: str) -> str:
    await signup(client, email)
    return await create_tenant(client, tenant_name)
