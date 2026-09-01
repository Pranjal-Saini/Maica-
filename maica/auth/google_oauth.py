import secrets
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthError(Exception):
    """Raised when the authorization code exchange or userinfo fetch fails —
    a network error, a non-2xx response, or an unexpected payload shape."""


class GoogleUserInfo(BaseModel):
    sub: str
    email: str
    email_verified: bool = False
    name: str | None = None


def generate_state() -> str:
    """A CSRF token: stashed in the session before redirecting to Google,
    checked against the value Google echoes back on the callback."""
    return secrets.token_urlsafe(32)


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{_AUTHORIZATION_URL}?{urlencode(params)}"


async def exchange_code_for_user_info(
    *, code: str, client_id: str, client_secret: str, redirect_uri: str
) -> GoogleUserInfo:
    """Exchanges the authorization code for an access token, then calls
    Google's userinfo endpoint with it. Reading user identity from Google's
    own HTTPS endpoint (rather than decoding the ID token ourselves) avoids
    needing a JWT/JWKS library just for this."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            userinfo_response = await client.get(
                _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo_response.raise_for_status()
            return GoogleUserInfo.model_validate(userinfo_response.json())
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise GoogleOAuthError(f"Google OAuth exchange failed: {exc}") from exc
