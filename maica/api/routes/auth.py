from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.deps import get_current_user, get_db_session
from maica.auth import repository as auth_repository
from maica.auth.models import User
from maica.auth.security import hash_password, verify_password
from maica.web.templating import templates

router = APIRouter()


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "signup.html", {"error": None})


@router.post("/signup", response_model=None)
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    existing = await auth_repository.get_user_by_email(session, email)
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": "An account with that email already exists."},
            status_code=400,
        )

    user = await auth_repository.create_user(session, email, hash_password(password))
    await session.commit()
    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_model=None)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    user = await auth_repository.get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Incorrect email or password."}, status_code=400
        )

    request.session["user_id"] = str(user.id)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    tenants = await auth_repository.list_tenants_for_user(session, user.id)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user, "tenants": tenants})


@router.get("/tenants/new", response_class=HTMLResponse)
async def new_tenant_form(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "new_tenant.html", {"error": None})


@router.post("/tenants")
async def create_tenant(
    request: Request,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    tenant = await auth_repository.create_tenant_for_user(session, user.id, name)
    await session.commit()
    return RedirectResponse(
        url=f"/tenants/{tenant.id}/analyses", status_code=status.HTTP_303_SEE_OTHER
    )
