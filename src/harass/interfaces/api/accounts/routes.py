"""Same-origin cookie authentication routes and owner dependency."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from harass.application.accounts.authentication import ManageAuthentication
from harass.application.accounts.errors import (
    AuthenticationError,
    EmailRegisteredError,
    InvalidEmailError,
    InvalidNameError,
    PasswordRejectedError,
    RegistrationError,
)
from harass.application.ports.accounts import RequestLimiter
from harass.interfaces.api.accounts.cookies import COOKIE_NAME, REFRESH_COOKIE_NAME, SessionCookies
from harass.interfaces.api.accounts.dependencies import authenticated_user
from harass.interfaces.api.accounts.policy import install_auth_policy
from harass.interfaces.api.accounts.schemas import (
    LoginRequest,
    ProfileUpdateRequest,
    SessionResponse,
    SignupRequest,
    UserResponse,
    public_user,
)


def _service(request: Request) -> ManageAuthentication:
    """Return the authentication use case installed on the application."""
    return cast(ManageAuthentication, request.app.state.authentication)


def _cookies(request: Request) -> SessionCookies:
    """Return the cookie settings installed on the application."""
    return cast(SessionCookies, request.app.state.cookies)


Service = Annotated[ManageAuthentication, Depends(_service)]
Cookies = Annotated[SessionCookies, Depends(_cookies)]
router = APIRouter(prefix="/auth")


def install_auth(
    app: FastAPI,
    authentication: ManageAuthentication,
    *,
    secure_cookie: bool = False,
    session_seconds: int = 900,
    request_limiter: RequestLimiter | None = None,
) -> None:
    """Install revocable JWT cookies and same-origin mutation checks.

    OWASP CSRF guidance permits a required custom header for same-origin JSON
    APIs. No CORS permissions are granted; foreign Origin or Fetch Metadata is
    rejected.
    """
    app.state.authentication = authentication
    app.state.cookies = SessionCookies(secure_cookie, session_seconds)
    install_auth_policy(app, authenticated_user, request_limiter)

    @app.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, error: AuthenticationError) -> JSONResponse:
        """Return a generic unauthorized response for invalid credentials."""
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required."},
            headers={"Cache-Control": "no-store"},
        )

    app.include_router(router)


# Each signup failure has a code the page shows in Arabic; the request schema
# already rejects a password of the wrong length. A registered email is told
# apart on purpose, by the product's choice, so the visitor can sign in
# instead; this reveals that the address has an account.
SIGNUP_FAILURES: dict[type[RegistrationError], tuple[int, str]] = {
    EmailRegisteredError: (409, "email_registered"),
    InvalidEmailError: (400, "invalid_email"),
    InvalidNameError: (400, "invalid_name"),
    PasswordRejectedError: (400, "password_rejected"),
}


@router.post("/signup", response_model=UserResponse, status_code=201)
async def signup(
    body: SignupRequest, request: Request, service: Service, cookies: Cookies
) -> JSONResponse:
    """Create an account and set its session cookies."""
    try:
        result = await run_in_threadpool(service.signup, body.full_name, body.email, body.password)
    except RegistrationError as error:
        status, code = SIGNUP_FAILURES.get(type(error), (400, "registration_rejected"))
        return JSONResponse(status_code=status, content={"code": code})
    await run_in_threadpool(_logout, service, request)
    response = cookies.response(result)
    response.status_code = 201
    return response


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest, request: Request, service: Service, cookies: Cookies
) -> JSONResponse:
    """Authenticate account credentials and replace the browser session."""
    try:
        result = await run_in_threadpool(service.login, body.email, body.password)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    await run_in_threadpool(_logout, service, request)
    return cookies.response(result)


@router.get("/me", response_model=UserResponse)
async def me(request: Request) -> UserResponse:
    """Return the authenticated account's public identity."""
    return public_user(await authenticated_user(request))


@router.patch("/me", response_model=UserResponse)
async def rename(body: ProfileUpdateRequest, request: Request, service: Service) -> UserResponse:
    """Change the authenticated account's display name."""
    await authenticated_user(request)
    try:
        user = await run_in_threadpool(service.rename, _access_token(request), body.full_name)
    except RegistrationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return public_user(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, service: Service, cookies: Cookies) -> Response:
    """Revoke the browser credentials and clear both session cookies."""
    await run_in_threadpool(_logout, service, request)
    return cookies.clear()


@router.post("/refresh", response_model=UserResponse)
async def refresh(request: Request, service: Service, cookies: Cookies) -> Response:
    """Rotate refresh credentials within their absolute lifetime."""
    try:
        result = await run_in_threadpool(
            service.refresh, request.cookies.get(REFRESH_COOKIE_NAME, "")
        )
    except AuthenticationError:
        return cookies.clear(status=401)
    return cookies.response(result)


@router.get("/sessions", response_model=list[SessionResponse])
async def sessions(request: Request, service: Service) -> list[SessionResponse]:
    """List only the authenticated account's active sessions."""
    token = _access_token(request)
    user = await authenticated_user(request)
    current = service.session_identifier(token)
    rows = await run_in_threadpool(service.sessions, token)
    return [
        SessionResponse(
            session_id=row.session_id,
            created_at=row.created_at,
            expires_at=row.refresh_expires_at or row.expires_at,
            current=row.session_id == current,
        )
        for row in rows
        if row.user_id == user.user_id
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke(session_id: str, request: Request, service: Service) -> Response:
    """Revoke one session belonging to the authenticated account."""
    await authenticated_user(request)
    await run_in_threadpool(service.revoke_sessions, _access_token(request), session_id)
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
async def logout_all(request: Request, service: Service, cookies: Cookies) -> Response:
    """Invalidate every access and refresh session of the account."""
    await authenticated_user(request)
    await run_in_threadpool(service.revoke_sessions, _access_token(request))
    return cookies.clear()


def _access_token(request: Request) -> str:
    """Return the access cookie, or empty text when the browser sent none."""
    return request.cookies.get(COOKIE_NAME, "")


def _logout(service: ManageAuthentication, request: Request) -> None:
    """Revoke both cookies' credentials even when the access token expired."""
    service.logout(_access_token(request))
    service.logout_refresh(request.cookies.get(REFRESH_COOKIE_NAME, ""))
