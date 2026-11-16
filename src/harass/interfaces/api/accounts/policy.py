"""Same-origin mutation checks and shared authentication request limits."""

from collections.abc import Awaitable, Callable
from time import monotonic

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from harass.application.ports.request_limiter import RequestLimiter
from harass.domain.authentication import User

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
AUTH_PATHS = frozenset(
    {
        "/auth/login",
        "/auth/signup",
        "/auth/refresh",
        "/auth/password/forgot",
        "/auth/password/reset",
        "/auth/email/verify",
    }
)
VERIFY_PREFIXES = (
    "/auth/sessions",
    "/auth/logout-all",
    "/auth/email/request-verification",
)
USER_LIMITS = {"runs": 3, "verify": 10}
AUTH_LIMIT = 10
NO_STORE_PREFIXES = ("/auth", "/connections", "/runs", "/evaluation-options")


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
        fields = ("loc", "msg", "type")
        detail = [
            {key: item[key] for key in fields} for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detail})

    async def auth_wait(request: Request) -> int:
        """Limit sign-in requests per client and per submitted account."""
        client = request.client.host if request.client else "unknown"
        if request_limiter is None:
            return _consume_local(auth_requests, client)
        wait = await _consume(request_limiter, f"auth:{client}", AUTH_LIMIT)
        email = await _submitted_email(request)
        if wait or email is None:
            return wait
        key = f"auth-account:{email}"
        return await _consume(request_limiter, key, AUTH_LIMIT)

    @app.middleware("http")
    async def protect_mutations(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Enforce same-origin access and shared operation rate limits."""
        if request.method in MUTATING_METHODS and _cross_origin(request):
            return _detail(403, "Same-origin request required.")
        wait = 0
        scope = _user_scope(request)
        if request.method == "POST" and request.url.path in AUTH_PATHS:
            wait = await auth_wait(request)
        elif scope is not None and request_limiter is not None:
            try:
                user = await authenticate_user(request)
            except HTTPException:
                return _detail(401, "Authentication required.")
            key = f"{scope}:{user.user_id}"
            wait = await _consume(request_limiter, key, USER_LIMITS[scope])
        if wait:
            return _limited_response(wait)
        response = await call_next(request)
        if request.url.path.startswith(NO_STORE_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
        return response


def _cross_origin(request: Request) -> bool:
    """Tell whether a mutation lacks proof that it came from this origin."""
    origin = request.headers.get("origin")
    expected_origin = str(request.base_url).rstrip("/")
    return (
        request.headers.get("x-harass-request") != "1"
        or (origin is not None and origin != expected_origin)
        or request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}
    )


def _user_scope(request: Request) -> str | None:
    """Name the per-account limit a signed-in mutation counts against."""
    path = request.url.path
    if request.method not in {"POST", "DELETE"}:
        return None
    if path == "/runs" or path.endswith(("/resume", "/cancel")):
        return "runs"
    if path.startswith(VERIFY_PREFIXES) or path.endswith("/verify"):
        return "verify"
    return None


async def _submitted_email(request: Request) -> str | None:
    """Read the normalized account email from a JSON body, if present."""
    try:
        body = await request.json()
    except ValueError:
        return None
    email = body.get("email") if isinstance(body, dict) else None
    if not isinstance(email, str) or len(email) > 254:
        return None
    return email.strip().lower()


async def _consume(limiter: RequestLimiter, key: str, limit: int) -> int:
    """Consume one request from a shared limit and return the wait."""
    return await run_in_threadpool(limiter.consume, key, limit)


def _detail(status_code: int, message: str) -> JSONResponse:
    """Return a short error body without echoing request content."""
    return JSONResponse(status_code=status_code, content={"detail": message})


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
