"""Regression tests for findings from the security audit.

Each of these encodes a specific weakness that was found and fixed, so it
cannot come back quietly. The comments say what the weakness actually let
someone do — a test named after a header teaches nobody why it matters.
"""

import base64
import json
import re

import pytest
from httpx import AsyncClient
from itsdangerous import TimestampSigner
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.main import create_app
from maica.config.settings import INSECURE_SESSION_KEY, get_settings
from tests.conftest import login_as, signup_with_tenant


@pytest.fixture
def production_like(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_the_app_refuses_to_start_on_the_published_session_key(
    production_like: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default is in .env.example, so a deploy that forgets the env var
    would sign sessions with a value anyone can read — and a forged cookie is
    a full login with access to every client account that user was granted."""
    monkeypatch.setenv("SESSION_SECRET_KEY", INSECURE_SESSION_KEY)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="still the development default"):
        create_app()


def test_a_real_key_starts_normally(production_like: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET_KEY", "a-real-secret-from-the-environment")
    get_settings.cache_clear()

    assert create_app() is not None


def test_development_is_allowed_to_use_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SESSION_SECRET_KEY", INSECURE_SESSION_KEY)
    get_settings.cache_clear()

    assert create_app() is not None
    get_settings.cache_clear()


async def test_every_response_carries_the_content_security_policy(client: AsyncClient) -> None:
    # The layer that limits the damage when escaping fails somewhere.
    response = await client.get("/login")

    policy = response.headers["content-security-policy"]
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"


async def test_no_page_loads_script_from_another_origin(client: AsyncClient) -> None:
    """Tailwind was fetched from a CDN on every page that renders client ledger
    evidence, so a CDN compromise was arbitrary JS in a consultant's session.
    It is vendored, and the policy no longer names an external script host."""
    response = await client.get("/login")

    assert "cdn.tailwindcss.com" not in response.text
    assert "script-src 'self' 'nonce-" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in _script_src(response.headers["content-security-policy"])


def _script_src(policy: str) -> str:
    return next(part for part in policy.split("; ") if part.startswith("script-src"))


async def test_inline_scripts_carry_the_nonce_the_policy_names(client: AsyncClient) -> None:
    """Without this the policy would block the app's own scripts, which is the
    failure mode that makes people put 'unsafe-inline' back."""
    response = await client.get("/login")

    nonce = _script_src(response.headers["content-security-policy"]).split("'nonce-")[1].strip("'")
    assert f'<script nonce="{nonce}">' in response.text


async def test_the_nonce_changes_per_request(client: AsyncClient) -> None:
    # A fixed nonce is the same as no nonce: injected markup could carry it.
    first = await client.get("/login")
    second = await client.get("/login")

    assert _script_src(first.headers["content-security-policy"]) != _script_src(
        second.headers["content-security-policy"]
    )


async def test_a_client_account_name_cannot_break_out_of_the_delete_confirmation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The name went into an onsubmit attribute, where Jinja's HTML escaping is
    the wrong escaper: the HTML parser decodes &#39; back to a quote before the
    JS parser sees it, closing the string literal. It is a data attribute now."""
    await login_as(client, db_session, "consultant@example.com")
    await client.post("/tenants", data={"name": "'+alert(1)+'"})

    dashboard = await client.get("/dashboard")

    assert "onsubmit" not in dashboard.text
    assert "+alert(1)+" not in dashboard.text.replace("&#39;+alert(1)+&#39;", "")


async def test_a_hostile_record_id_cannot_redirect_off_site(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Record ids come verbatim from an uploaded CSV. An id of
    "../../..//evil.com" produced a Location the browser resolved to
    //evil.com — protocol-relative, off-site."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    hostile = "../../../../..//evil.com"
    notes = (
        b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Context,Type\n"
        + hostile.encode()
        + b",Invoice,7/12/2026 09:15,Account,4000,4010,System,SCHEDULED,Change\n"
    )
    analysis_id = (
        await client.post(
            f"/tenants/{tenant_id}/uploads", files={"files": ("n.csv", notes, "text/csv")}
        )
    ).json()["analysis_id"]

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/records", params={"q": hostile}
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert "//evil.com" not in location
    assert location.startswith(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/")


async def test_a_tampered_session_is_rejected_not_a_server_error(client: AsyncClient) -> None:
    """uuid.UUID() on a non-UUID raised ValueError, which surfaced as a 500.
    A cookie that does not parse is an authentication failure.

    Deliberately does not use login_as(), which stubs out get_current_user —
    the point is to exercise the real dependency against a real cookie.
    """
    signer = TimestampSigner(get_settings().session_secret_key)
    forged = signer.sign(base64.b64encode(json.dumps({"user_id": "not-a-uuid"}).encode()))
    client.cookies.set("session", forged.decode())

    response = await client.get("/dashboard")

    assert response.status_code == 401


async def test_too_many_files_in_one_upload_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Starlette allows 1,000 parts by default, each spooled to disk and then
    # read whole into memory here.
    from maica.api.routes.uploads import MAX_FILES_PER_UPLOAD

    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    row = b"Internal ID,Date,Type,Name,Amount,Account,Memo\n1,1/1/2026,Bill,X,1.00,4000,m\n"
    files = [("files", (f"f{i}.csv", row, "text/csv")) for i in range(MAX_FILES_PER_UPLOAD + 1)]

    response = await client.post(f"/tenants/{tenant_id}/uploads", files=files)

    assert response.status_code == 422
    assert "limit" in response.text


async def test_an_oversized_upload_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from maica.api.routes.uploads import MAX_UPLOAD_BYTES

    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    header = b"Internal ID,Date,Type,Name,Amount,Account,Memo\n"
    padded = header + b"1,1/1/2026,Bill,X,1.00,4000," + b"m" * (MAX_UPLOAD_BYTES + 1024) + b"\n"

    response = await client.post(
        f"/tenants/{tenant_id}/uploads", files={"files": ("big.csv", padded, "text/csv")}
    )

    assert response.status_code == 422
    assert "MB" in response.text


async def test_an_unreadable_csv_is_a_named_gap_not_a_crash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """csv raises on a field over its 128 KB limit. An uploaded export is
    untrusted input, so that has to read as "this file is unreadable", not as
    the tool falling over."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    huge_field = b"x" * 200_000
    csv_bytes = (
        b"Internal ID,Date,Type,Name,Amount,Account,Memo\n"
        b"1,1/1/2026,Bill,X,1.00,4000," + huge_field + b"\n"
    )

    response = await client.post(
        f"/tenants/{tenant_id}/uploads", files={"files": ("bad.csv", csv_bytes, "text/csv")}
    )

    assert response.status_code == 422
    assert "could not read this CSV" in response.text


async def test_deleting_without_a_csrf_token_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SameSite=strict already blocks the cross-site POST. This is the second
    lock, because SameSite is one attribute away from being loosened for an
    unrelated reason and nothing would fail loudly when it was."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.post(f"/tenants/{tenant_id}/delete")

    assert response.status_code == 403
    assert "expired or was not submitted from this site" in response.text


async def test_deleting_with_the_session_token_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The token has to actually work, or the protection is just an outage.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    dashboard = await client.get("/dashboard")
    token = re.search(r'name="csrf_token" value="([^"]+)"', dashboard.text).group(1)

    response = await client.post(f"/tenants/{tenant_id}/delete", data={"csrf_token": token})

    assert response.status_code == 303


async def test_a_token_from_another_session_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    await client.get("/dashboard")

    response = await client.post(
        f"/tenants/{tenant_id}/delete", data={"csrf_token": "borrowed-from-elsewhere"}
    )

    assert response.status_code == 403


async def test_an_overlong_client_account_name_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The name goes into every card, the PDF header and the delete
    # confirmation; unbounded it is a free way to make those unreadable.
    await login_as(client, db_session, "consultant@example.com")
    page = await client.get("/tenants/new")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)

    response = await client.post("/tenants", data={"name": "x" * 500, "csrf_token": token})

    assert response.status_code == 422
