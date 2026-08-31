import os
from collections.abc import AsyncGenerator

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://maica:maica@localhost:5432/maica_test")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from maica.api.deps import get_db_session
from maica.api.main import create_app
from maica.config.settings import get_settings
from maica.evidence.db import Base
from maica.evidence.models import Analysis, RawEvidence, Record, Tenant


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
        await session.execute(delete(Tenant))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
