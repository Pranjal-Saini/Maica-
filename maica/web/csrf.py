"""A per-session token on the state-changing forms.

Cross-site forgery is currently prevented by the session cookie's SameSite
setting, which is real protection but the wrong thing to rely on alone: it is
one attribute away from being switched off for an unrelated reason (embedding a
page, a third-party integration), and nothing would fail loudly when it was.

The forms that matter are the ones that destroy data — deleting a client
account takes every analysis and every uploaded row with it.
"""

import secrets

from fastapi import HTTPException, Request, status

SESSION_KEY = "csrf_token"
FORM_FIELD = "csrf_token"


def issue_token(request: Request) -> str:
    """The session's token, minted on first use and stable thereafter.

    Stable per session rather than per form: a rotating token breaks the back
    button and any second tab, and buys nothing here — the secret is the
    session cookie, which an attacker's page cannot read.
    """
    token = request.session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = token
    return str(token)


def verify(request: Request, submitted: str | None) -> None:
    """Rejects a POST whose token does not match the session's.

    Compared with compare_digest so a wrong token cannot be recovered a
    character at a time from response timing.
    """
    expected = request.session.get(SESSION_KEY)
    if not expected or not submitted or not secrets.compare_digest(str(expected), submitted):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This form has expired or was not submitted from this site. Reload and retry.",
        )
