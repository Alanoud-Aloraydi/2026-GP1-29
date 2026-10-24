"""Same-origin mutation checks and shared authentication request limits."""

from collections.abc import Awaitable, Callable
from time import monotonic

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from harass.application.ports.request_limiter import RequestLimiter
from harass.domain.authentication import User


def install_auth_policy(
    app: FastAPI,
    authenticate_user: Callable[[Request], Awaitable[User]],
    request_limiter: RequestLimiter | None,
) -> None:
    """Install bounded mutation admission before route handlers execute."""
    auth_requests: dict[str, tuple[float, int]] = {}

    @app.exception_handler(RequestValidationError)
    async def hide_validation_inputs(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        """Retain validation locations while omitting submitted values."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "loc": list(item["loc"]),
                        "msg": item["msg"],
                        "type": item["type"],
                    }
                    for item in error.errors()
                ]
            },
        )

    @app.middleware("http")
    async def protect_mutations(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Enforce same-origin access and shared operation rate limits."""
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected_origin = str(request.base_url).rstrip("/")
            if (
                request.headers.get("x-harass-request") != "1"
                or (origin is not None and origin != expected_origin)
                or request.headers.get("sec-fetch-site")
                in {"cross-site", "same-site"}
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Same-origin request required."},
                )
        if request.method == "POST" and request.url.path in {
            "/auth/login",
            "/auth/signup",
            "/auth/refresh",
            "/auth/password/forgot",
            "/auth/password/reset",
            "/auth/email/verify",
        }:
            client = request.client.host if request.client else "unknown"
            if request_limiter is not None:
                wait = await run_in_threadpool(
                    request_limiter.consume, f"auth:{client}", 10
                )
                if wait:
                    return _limited_response(wait)
                try:
                    body = await request.json()
                except ValueError:
                    body = {}
                email = body.get("email") if isinstance(body, dict) else None
                if isinstance(email, str) and len(email) <= 254:
                    wait = await run_in_threadpool(
                        request_limiter.consume,
                        f"auth-account:{email.strip().lower()}",
                        10,
                    )
                    if wait:
                        return _limited_response(wait)
            else:
                wait = _consume_local(auth_requests, client)
                if wait:
                    return _limited_response(wait)
        elif (
            request_limiter is not None
            and request.method in {"POST", "DELETE"}
            and (
                request.url.path.startswith(
                    (
                        "/auth/password",
                        "/auth/sessions",
                        "/auth/logout-all",
                        "/auth/email/request-verification",
                    )
                )
                or request.url.path == "/runs"
                or request.url.path.endswith(("/verify", "/resume", "/cancel"))
            )
        ):
            try:
                user = await authenticate_user(request)
            except HTTPException:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required."},
                )
            scope = (
                "runs"
                if request.url.path == "/runs"
                or request.url.path.endswith(("/resume", "/cancel"))
                else "verify"
            )
            wait = await run_in_threadpool(
                request_limiter.consume,
                f"{scope}:{user.user_id}",
                3 if scope == "runs" else 10,
            )
            if wait:
                return _limited_response(wait)
        response = await call_next(request)
        if request.url.path.startswith(
            ("/auth", "/connections", "/runs", "/evaluation-options")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response


def _limited_response(wait: int) -> JSONResponse:
    """Return a noncacheable retry interval for exceeded request limits."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Try again later."},
        headers={"Retry-After": str(wait), "Cache-Control": "no-store"},
    )


def _consume_local(requests: dict[str, tuple[float, int]], client: str) -> int:
    """Bound authentication requests in isolated nonpersistent fixtures."""
    now = monotonic()
    for key in list(requests):
        if now - requests[key][0] >= 60:
            del requests[key]
    start, count = requests.get(client, (now, 0))
    if count >= 10 or (client not in requests and len(requests) >= 4096):
        return 60
    requests[client] = (start, count + 1)
    return 0
