"""Browser security headers for same-origin HTML and authenticated API."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from starlette.responses import Response


def install_security_headers(app: FastAPI, secure_cookie: bool) -> None:
    """Apply browser isolation and transport headers to every response."""

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Apply browser isolation and configured HTTPS transport policy."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        if request.url.path not in {
            "/docs",
            "/redoc",
            "/docs/oauth2-redirect",
        }:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; "
                "style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; "
                "object-src 'none'; base-uri 'self'; "
                "form-action 'self'"
            )
        if secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
