"""Response headers that constrain what a page is allowed to do.

Every authenticated page here renders a client's ledger evidence, so the cost
of one XSS is a consultant's whole account. These headers are the layer that
limits the blast radius when escaping fails somewhere — which it did, in the
delete confirmation, before this was written.

`Content-Security-Policy` is the substantive one: with the Tailwind build
vendored into static/, `script-src` no longer names an external host, so a
compromised third party cannot execute on a page showing client data.
"""

import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Google Fonts serves the wordmark's fallback face. Everything else is 'self'.
_FONT_CSS = "https://fonts.googleapis.com"
_FONT_FILES = "https://fonts.gstatic.com"


#: Every inline <script> in the templates carries this request's nonce, so the
#: policy can name them individually instead of allowing inline script wholesale.
#: That is what makes CSP an actual XSS control rather than a way of blocking
#: third-party hosts: injected markup has no way to guess the nonce.
#:
#: style-src still needs 'unsafe-inline' — Tailwind's Play build writes styles
#: into the document at runtime, and it cannot be nonced. Removing that needs the
#: compiled-stylesheet build step described in static/vendor/README.md.
def _policy(nonce: str) -> str:
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            f"style-src 'self' 'unsafe-inline' {_FONT_CSS}",
            f"font-src 'self' {_FONT_FILES}",
            "img-src 'self' data:",
            "connect-src 'self'",
            "form-action 'self'",
            "base-uri 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
        ]
    )


class SecurityHeadersMiddleware:
    """Applies the policy to every response.

    `https_only` also decides HSTS: asserting it while the app is served over
    plain HTTP in development would pin the browser to a scheme that is not
    being served.
    """

    def __init__(self, app: ASGIApp, *, https_only: bool) -> None:
        self.app = app
        self._https_only = https_only

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # One nonce per request, readable by the templates as
        # request.state.csp_nonce and named in this response's policy.
        nonce = secrets.token_urlsafe(16)
        scope.setdefault("state", {})["csp_nonce"] = nonce

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                for name, value in self.headers(nonce):
                    headers.append((name.encode("latin-1"), value.encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def headers(self, nonce: str) -> list[tuple[str, str]]:
        values = [
            ("content-security-policy", _policy(nonce)),
            ("x-content-type-options", "nosniff"),
            ("referrer-policy", "same-origin"),
            ("x-frame-options", "DENY"),
        ]
        if self._https_only:
            values.append(("strict-transport-security", "max-age=31536000; includeSubDomains"))
        return values
