"""Same-origin cookie authentication routes and owner dependency."""

from collections.abc import Awaitable, Callable
from time import monotonic
from typing import cast

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from harass.application.ports.request_limiter import RequestLimiter
from harass.application.use_cases.manage_authentication import (
    AuthenticationError,
    ManageAuthentication,
    PasswordRejectedError,
    RegistrationError,
)
from harass.domain.authentication import AuthenticatedLogin, User

COOKIE_NAME = "harass_session"


class LoginRequest(BaseModel):
    """Bound login inputs with password excluded from representations."""

    model_config = ConfigDict(hide_input_in_errors=True, extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)


class SignupRequest(LoginRequest):
    """Account creation with a long password rather than composition rules."""

    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=15, max_length=128, repr=False)


class UserResponse(BaseModel):
    """Public account details; no password hash or session token."""

    user_id: str
    full_name: str
    email: str


async def authenticated_owner(request: Request) -> str:
    """Resolve ownership exclusively from a valid authenticated cookie."""
    user = await _authenticated_user(request)
    return user.user_id


async def _authenticated_user(request: Request) -> User:
    authentication = cast(
        ManageAuthentication | None, getattr(request.app.state, "authentication", None)
    )
    token = request.cookies.get(COOKIE_NAME)
    if authentication is None or token is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        return await run_in_threadpool(authentication.authenticate, token)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail="Session is invalid or expired.") from error


def install_auth(
    app: FastAPI,
    authentication: ManageAuthentication,
    *,
    secure_cookie: bool = False,
    session_seconds: int = 3600,
    request_limiter: RequestLimiter | None = None,
) -> None:
    """Install revocable JWT cookies and same-origin mutation checks.

    OWASP CSRF guidance permits a required custom header for same-origin JSON APIs.
    No CORS permissions are granted; foreign Origin or Fetch Metadata is rejected.
    """
    app.state.authentication = authentication
    # Isolated fixtures retain a bounded local fallback; production injects shared storage.
    auth_requests: dict[str, tuple[float, int]] = {}

    @app.exception_handler(RequestValidationError)
    async def hide_validation_inputs(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ]
            },
        )

    @app.middleware("http")
    async def protect_mutations(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            expected_origin = str(request.base_url).rstrip("/")
            if (
                request.headers.get("x-harass-request") != "1"
                or (origin is not None and origin != expected_origin)
                or request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}
            ):
                return JSONResponse(
                    status_code=403, content={"detail": "Same-origin request required."}
                )
        if request.method == "POST" and request.url.path in {"/auth/login", "/auth/signup"}:
            client = request.client.host if request.client else "unknown"
            if request_limiter is not None:
                wait = await run_in_threadpool(request_limiter.consume, f"auth:{client}", 10)
                if wait:
                    return _limited_response(wait)
                try:
                    body = await request.json()
                except ValueError:
                    body = {}
                email = body.get("email") if isinstance(body, dict) else None
                if isinstance(email, str) and len(email) <= 254:
                    wait = await run_in_threadpool(
                        request_limiter.consume, f"auth-account:{email.strip().lower()}", 10
                    )
                    if wait:
                        return _limited_response(wait)
            else:
                wait = _consume_local(auth_requests, client)
                if wait:
                    return _limited_response(wait)
        elif (
            request_limiter is not None
            and request.method == "POST"
            and (
                request.url.path == "/runs"
                or request.url.path.endswith(("/verify", "/resume", "/cancel"))
            )
        ):
            try:
                user = await _authenticated_user(request)
            except HTTPException:
                return JSONResponse(
                    status_code=401, content={"detail": "Authentication required."}
                )
            scope = (
                "runs"
                if request.url.path == "/runs" or request.url.path.endswith(("/resume", "/cancel"))
                else "verify"
            )
            wait = await run_in_threadpool(
                request_limiter.consume, f"{scope}:{user.user_id}", 3 if scope == "runs" else 10
            )
            if wait:
                return _limited_response(wait)
        response = await call_next(request)
        if request.url.path.startswith(("/auth", "/connections", "/runs", "/evaluation-options")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def session_response(login: AuthenticatedLogin) -> JSONResponse:
        response = JSONResponse(content=_public_user(login.user).model_dump())
        response.set_cookie(
            COOKIE_NAME,
            login.token,
            max_age=session_seconds,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
        )
        return response

    @app.post("/auth/signup", response_model=UserResponse, status_code=201)
    async def signup(body: SignupRequest, request: Request) -> JSONResponse:
        try:
            result = await run_in_threadpool(
                authentication.signup, body.full_name, body.email, body.password
            )
        except PasswordRejectedError:
            return JSONResponse(status_code=400, content={"code": "password_rejected"})
        except RegistrationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        await run_in_threadpool(authentication.logout, request.cookies.get(COOKIE_NAME, ""))
        response = session_response(result)
        response.status_code = 201
        return response

    @app.post("/auth/login", response_model=UserResponse)
    async def login(body: LoginRequest, request: Request) -> JSONResponse:
        try:
            result = await run_in_threadpool(authentication.login, body.email, body.password)
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        await run_in_threadpool(authentication.logout, request.cookies.get(COOKIE_NAME, ""))
        return session_response(result)

    @app.get("/auth/me", response_model=UserResponse)
    async def me(request: Request) -> UserResponse:
        return _public_user(await _authenticated_user(request))

    @app.post("/auth/logout", status_code=204)
    async def logout(request: Request) -> Response:
        await run_in_threadpool(authentication.logout, request.cookies.get(COOKIE_NAME, ""))
        response = Response(status_code=204)
        response.delete_cookie(
            COOKIE_NAME, path="/", secure=secure_cookie, httponly=True, samesite="strict"
        )
        return response


def _public_user(user: User) -> UserResponse:
    return UserResponse(user_id=user.user_id, full_name=user.full_name, email=user.email)


def _limited_response(wait: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Try again later."},
        headers={"Retry-After": str(wait), "Cache-Control": "no-store"},
    )


def _consume_local(requests: dict[str, tuple[float, int]], client: str) -> int:
    now = monotonic()
    for key in list(requests):
        if now - requests[key][0] >= 60:
            del requests[key]
    start, count = requests.get(client, (now, 0))
    if count >= 10 or (client not in requests and len(requests) >= 4096):
        return 60
    requests[client] = (start, count + 1)
    return 0
