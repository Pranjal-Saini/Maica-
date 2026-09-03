from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from maica.api.errors import ingest_validation_error_handler
from maica.api.routes import analyses, auth, health, manage, uploads
from maica.config.logging import configure_logging
from maica.config.settings import get_settings
from maica.evidence.db import get_engine
from maica.ingest.errors import IngestValidationError


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="MAICA — NetSuite Transaction Impact Copilot", lifespan=_lifespan)

    app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret_key)
    app.mount("/static", StaticFiles(directory="maica/web/static"), name="static")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(uploads.router)
    app.include_router(analyses.router)
    app.include_router(manage.router)
    app.add_exception_handler(IngestValidationError, ingest_validation_error_handler)

    return app


app = create_app()
