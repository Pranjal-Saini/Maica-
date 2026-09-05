"""The CSRF token behind the destructive forms.

SameSite=strict already blocks the cross-site POST, so this is the second lock
rather than the first. It exists because SameSite is one attribute away from
being loosened for an unrelated reason — embedding a page, a third-party
integration — and nothing would fail loudly when it was.
"""

import pytest
from fastapi import HTTPException

from maica.web.csrf import SESSION_KEY, issue_token, verify


class _FakeRequest:
    """csrf only touches request.session."""

    def __init__(self, session: dict | None = None) -> None:
        self.session = session if session is not None else {}


def test_a_token_is_minted_once_and_then_reused() -> None:
    # Rotating per form would break the back button and any second tab, and
    # buys nothing: the secret is the session cookie, which an attacker's page
    # cannot read.
    request = _FakeRequest()

    first = issue_token(request)  # type: ignore[arg-type]
    second = issue_token(request)  # type: ignore[arg-type]

    assert first == second
    assert request.session[SESSION_KEY] == first


def test_two_sessions_get_different_tokens() -> None:
    a = issue_token(_FakeRequest())  # type: ignore[arg-type]
    b = issue_token(_FakeRequest())  # type: ignore[arg-type]

    assert a != b


def test_the_token_is_long_enough_to_be_unguessable() -> None:
    assert len(issue_token(_FakeRequest())) >= 32  # type: ignore[arg-type]


def test_the_matching_token_passes() -> None:
    request = _FakeRequest()
    token = issue_token(request)  # type: ignore[arg-type]

    verify(request, token)  # type: ignore[arg-type]  # does not raise


@pytest.mark.parametrize(
    "submitted",
    [None, "", "wrong", " "],
    ids=["missing", "empty", "wrong", "whitespace"],
)
def test_anything_other_than_the_session_token_is_refused(submitted: str | None) -> None:
    request = _FakeRequest()
    issue_token(request)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as raised:
        verify(request, submitted)  # type: ignore[arg-type]

    assert raised.value.status_code == 403


def test_a_session_with_no_token_refuses_even_a_plausible_one() -> None:
    # Otherwise an attacker could supply both halves of the comparison.
    with pytest.raises(HTTPException) as raised:
        verify(_FakeRequest(), "some-token")  # type: ignore[arg-type]

    assert raised.value.status_code == 403


def test_the_refusal_tells_the_user_what_to_do() -> None:
    # A bare 403 on a delete button reads as a broken app; most of the time it
    # is a stale tab, not an attack.
    with pytest.raises(HTTPException) as raised:
        verify(_FakeRequest(), "nope")  # type: ignore[arg-type]

    assert "Reload" in str(raised.value.detail)
