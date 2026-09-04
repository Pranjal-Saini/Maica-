"""Response headers that constrain what a page is allowed to do.

Every authenticated page here renders a client's ledger evidence, so the cost
of one XSS is a consultant's whole account. These headers are the layer that
limits the blast radius when escaping fails somewhere — which it did, in the
delete confirmation, before this was written.

`Content-Security-Policy` is the substantive one: with the Tailwind build
vendored into static/, `script-src` no longer names an external host, so a
compromised third party cannot execute on a page showing client data.
"""

from starlette.types import ASGIApp

#: Google Fonts serves the wordmark's fallback face. Everything else is 'self'.
_FONT_CSS = "https://fonts.googleapis.com"
_FONT_FILES = "https://fonts.gstatic.com"

#: 'unsafe-inline' for scripts is a real weakening and is here on purpose: the
#: templates carry inline <script> blocks, and replacing it with per-request
#: nonces means threading one through every template that has one. It still
#: blocks loading script from another origin, which is what the vendoring was
#: for. Nonces are the next step, not a substitute for it.
_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
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

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                for name, value in self.headers():
                    headers.append((name.encode("latin-1"), value.encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def headers(self) -> list[tuple[str, str]]:
        values = [
            ("content-security-policy", _POLICY),
            ("x-content-type-options", "nosniff"),
            ("referrer-policy", "same-origin"),
            ("x-frame-options", "DENY"),
        ]
        if self._https_only:
            values.append(("strict-transport-security", "max-age=31536000; includeSubDomains"))
        return values
