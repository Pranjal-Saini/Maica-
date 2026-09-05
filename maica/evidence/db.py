from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from maica.config.settings import get_settings


class Base(DeclarativeBase):
    pass


# pool_pre_ping: the pool hands out connections it opened earlier, and a
# database restart or an idle-timeout on managed Postgres leaves those dead.
# Without the ping every request then fails until the app itself is restarted —
# a database that came back stays "down" from the outside. One round trip per
# checkout is worth not turning a recovered database into an outage.
_engine = create_async_engine(get_settings().database_url, future=True, pool_pre_ping=True)
async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    return _engine


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
