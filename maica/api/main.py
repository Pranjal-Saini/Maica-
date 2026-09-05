from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from maica.api.errors import ingest_validation_error_handler
from maica.api.routes import (
    analyses,
    auth,
    deep_dive,
    health,
    investigate,
    manage,
    uploads,
)
from maica.api.security_headers import SecurityHeadersMiddleware
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

    settings = get_settings()
    if settings.session_key_is_insecure and not settings.is_development:
        # The default is published in .env.example, so a deploy that forgets the
        # env var would sign sessions with a value anyone can read — and a forged
        # cookie is a full login. Failing to boot is the safe direction.
        raise RuntimeError(
            "SESSION_SECRET_KEY is still the development default. Set it before "
            f"running with ENVIRONMENT={settings.environment!r}."
        )

    app.add_middleware(SecurityHeadersMiddleware, https_only=not settings.is_development)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        # Starlette only adds `Secure` when https_only is set, so without this the
        # session travels in cleartext over any plain-HTTP request to the host.
        https_only=not settings.is_development,
        # Lax, not strict. Strict withholds the cookie on every cross-site
        # top-level navigation — including Google's redirect back to
        # /auth/callback, which leaves oauth_state unreadable and makes sign-in
        # fail for everyone. Lax still withholds it from cross-site POSTs,
        # which is the CSRF property that matters, and the state-changing
        # routes now carry their own tokens rather than relying on it alone.
        same_site="lax",
    )
    app.mount("/static", StaticFiles(directory="maica/web/static"), name="static")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(uploads.router)
    app.include_router(analyses.router)
    app.include_router(manage.router)
    app.include_router(deep_dive.router)
    app.include_router(investigate.router)
    app.add_exception_handler(IngestValidationError, ingest_validation_error_handler)

    return app


app = create_app()
