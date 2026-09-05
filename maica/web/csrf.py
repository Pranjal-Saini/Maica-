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

#: Accepted as an alternative to the form field, for requests issued by script
#: rather than by a submitted form. It is not a weaker channel: a cross-site
#: page cannot set a custom header without turning the request into a
#: preflighted one, which same-origin policy then refuses.
HEADER_FIELD = "X-CSRF-Token"


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
    # The form field wins when present, even when it is wrong: a submitted-but-
    # wrong token is a failure, not an invitation to look somewhere else.
    if submitted is None:
        submitted = request.headers.get(HEADER_FIELD)

    expected = request.session.get(SESSION_KEY)
    # Compared as bytes: compare_digest raises TypeError on non-ASCII strings,
    # so a token of 'e-acute' turned a 403 into a 500 inside the check itself.
    matches = (
        bool(expected)
        and bool(submitted)
        and secrets.compare_digest(str(expected).encode("utf-8"), str(submitted).encode("utf-8"))
    )
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This form has expired or was not submitted from this site. Reload and retry.",
        )
