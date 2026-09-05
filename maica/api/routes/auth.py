from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_current_user, get_db_session
from maica.auth import repository as auth_repository
from maica.auth.google_oauth import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_code_for_user_info,
    generate_state,
)
from maica.auth.models import User
from maica.config.settings import get_settings
from maica.evidence import repository as evidence_repository
from maica.web.csrf import FORM_FIELD
from maica.web.csrf import verify as verify_csrf
from maica.web.nav import page_context
from maica.web.templating import templates

router = APIRouter()

#: A client account name is a label, not a document. Unbounded, it goes into
#: every card, every PDF header and the delete confirmation.
MAX_TENANT_NAME = 120


@router.get("/")
async def root(request: Request) -> RedirectResponse:
    """Sends visitors somewhere useful instead of a bare 404. Reads the
    session directly rather than depending on get_current_user, which raises
    401 for anonymous visitors — here we just want to point them at login."""
    destination = "/dashboard" if request.session.get("user_id") else "/login"
    return RedirectResponse(url=destination, status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    settings = get_settings()
    google_configured = bool(settings.google_client_id and settings.google_client_secret)
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "google_configured": google_configured}
    )


@router.get("/auth/google/login", response_model=None)
async def google_login(request: Request) -> HTMLResponse | RedirectResponse:
    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Google Sign-In is not configured yet on this server.",
                "google_configured": False,
            },
            status_code=503,
        )

    state = generate_state()
    request.session["oauth_state"] = state
    url = build_authorization_url(
        client_id=settings.google_client_id,
        redirect_uri=settings.google_redirect_uri,
        state=state,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/google/callback", response_model=None)
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    settings = get_settings()
    expected_state = request.session.pop("oauth_state", None)
    google_configured = bool(settings.google_client_id and settings.google_client_secret)

    def _login_error(message: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": message, "google_configured": google_configured},
            status_code=400,
        )

    if error:
        return _login_error("Google sign-in was cancelled or denied.")
    if not code or not state or not expected_state or state != expected_state:
        return _login_error("Sign-in request could not be verified. Please try again.")
    if not (settings.google_client_id and settings.google_client_secret):
        return _login_error("Google Sign-In is not configured yet on this server.")

    try:
        google_user = await exchange_code_for_user_info(
            code=code,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
        )
    except GoogleOAuthError:
        return _login_error("Google sign-in failed. Please try again.")

    user = await auth_repository.get_or_create_user_from_google(session, google_user)
    await session.commit()
    # Drop anything the visitor accumulated before signing in — the oauth state,
    # a remembered nav context — rather than carrying it into their session.
    request.session.clear()
    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(
    request: Request, csrf_token: str = Form(None, alias=FORM_FIELD)
) -> RedirectResponse:
    # Forced logout is only an annoyance, but it is a state change driven by a
    # form and there is no reason for it to be the one that is unprotected.
    verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    tenants = await auth_repository.list_tenants_for_user(session, user.id)
    activity = await evidence_repository.get_activity_for_tenants(
        session, [tenant.id for tenant in tenants]
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_context(request, user=user, active="accounts", tenant_count=len(tenants))
        | {"tenants": tenants, "activity": activity},
    )


@router.get("/tenants/new", response_class=HTMLResponse)
async def new_tenant_form(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    tenants = await auth_repository.list_tenants_for_user(session, user.id)
    return templates.TemplateResponse(
        request,
        "new_tenant.html",
        page_context(request, user=user, active="accounts", tenant_count=len(tenants))
        | {"error": None},
    )


@router.post("/tenants")
async def create_tenant(
    request: Request,
    name: str = Form(..., max_length=MAX_TENANT_NAME),
    csrf_token: str = Form(None, alias=FORM_FIELD),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    tenant = await auth_repository.create_tenant_for_user(session, user.id, name.strip())
    await session.commit()
    return RedirectResponse(
        url=f"/tenants/{tenant.id}/analyses", status_code=status.HTTP_303_SEE_OTHER
    )
