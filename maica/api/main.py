from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from maica.api.errors import ingest_validation_error_handler
from maica.api.routes import health, uploads
from maica.config.logging import configure_logging
from maica.evidence.db import get_engine
from maica.ingest.errors import IngestValidationError


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="MAICA — NetSuite Transaction Impact Copilot", lifespan=_lifespan)

    app.include_router(health.router)
    app.include_router(uploads.router)
    app.add_exception_handler(IngestValidationError, ingest_validation_error_handler)

    return app


app = create_app()
