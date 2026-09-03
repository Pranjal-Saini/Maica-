"""One-shot messages that survive a redirect.

A delete finishes with a redirect, so the page that shows the result is a
different request from the one that did the work. The message rides in the
signed session and is removed the first time it is read, so a refresh does not
replay "deleted successfully" over something that was not just deleted.
"""

from starlette.requests import Request

SESSION_KEY = "flash"


def set_flash(request: Request, message: str) -> None:
    request.session[SESSION_KEY] = message


def pop_flash(request: Request) -> str | None:
    """Reads and clears. Called once per page render, from page_context()."""
    message = request.session.pop(SESSION_KEY, None)
    return str(message) if message else None
