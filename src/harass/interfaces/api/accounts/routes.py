"""Same-origin cookie authentication routes and owner dependency."""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from harass.application.accounts.authentication import ManageAuthentication
from harass.application.accounts.errors import (
    AuthenticationError,
    PasswordRejectedError,
    RegistrationError,
)
from harass.application.ports.request_limiter import RequestLimiter
from harass.domain.authentication import User
from harass.interfaces.api.accounts.cookies import (
    COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    SessionCookies,
)
from harass.interfaces.api.accounts.dependencies import authenticated_user
from harass.interfaces.api.accounts.policy import install_auth_policy
from harass.interfaces.api.accounts.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    SessionResponse,
    SignupRequest,
    UserResponse,
)


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
    install_auth_policy(app, authenticated_user, request_limiter)

    @app.exception_handler(AuthenticationError)
    async def authentication_error(
        _: Request, error: AuthenticationError
    ) -> JSONResponse:
        """Return a generic unauthorized response for invalid credentials."""
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required."},
            headers={"Cache-Control": "no-store"},
        )

    cookies = SessionCookies(secure_cookie, session_seconds)

    @app.post("/auth/signup", response_model=UserResponse, status_code=201)
    async def signup(body: SignupRequest, request: Request) -> JSONResponse:
        """Create an account and set its session cookies."""
        try:
            result = await run_in_threadpool(
                authentication.signup,
                body.full_name,
                body.email,
                body.password,
            )
        except PasswordRejectedError:
            return JSONResponse(
                status_code=400, content={"code": "password_rejected"}
            )
        except RegistrationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        await run_in_threadpool(_logout, authentication, request)
        response = cookies.response(result)
        response.status_code = 201
        return response

    @app.post("/auth/login", response_model=UserResponse)
    async def login(body: LoginRequest, request: Request) -> JSONResponse:
        """Authenticate account credentials and replace the browser session."""
        try:
            result = await run_in_threadpool(
                authentication.login, body.email, body.password
            )
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        await run_in_threadpool(_logout, authentication, request)
        return cookies.response(result)

    @app.get("/auth/me", response_model=UserResponse)
    async def me(request: Request) -> UserResponse:
        """Return the authenticated account's public identity."""
        return _public_user(await authenticated_user(request))

    @app.post("/auth/logout", status_code=204)
    async def logout(request: Request) -> Response:
        """Revoke the browser credentials and clear both session cookies."""
        await run_in_threadpool(_logout, authentication, request)
        return cookies.clear()

    @app.post("/auth/refresh", response_model=UserResponse)
    async def refresh(request: Request) -> Response:
        """Rotate refresh credentials within their absolute lifetime."""
        try:
            result = await run_in_threadpool(
                authentication.refresh,
                request.cookies.get(REFRESH_COOKIE_NAME, ""),
            )
        except AuthenticationError:
            return cookies.clear(status=401)
        return cookies.response(result)

    @app.get("/auth/sessions", response_model=list[SessionResponse])
    async def sessions(request: Request) -> list[SessionResponse]:
        """List only the authenticated account's active sessions."""
        token = request.cookies.get(COOKIE_NAME, "")
        user = await authenticated_user(request)
        current = authentication.session_identifier(token)
        rows = await run_in_threadpool(authentication.sessions, token)
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

    @app.delete("/auth/sessions/{session_id}", status_code=204)
    async def revoke(session_id: str, request: Request) -> Response:
        """Revoke one session belonging to the authenticated account."""
        await authenticated_user(request)
        await run_in_threadpool(
            authentication.revoke_sessions,
            request.cookies.get(COOKIE_NAME, ""),
            session_id,
        )
        return Response(status_code=204)

    @app.post("/auth/logout-all", status_code=204)
    async def logout_all(request: Request) -> Response:
        """Invalidate every access and refresh session of the account."""
        await authenticated_user(request)
        await run_in_threadpool(
            authentication.revoke_sessions,
            request.cookies.get(COOKIE_NAME, ""),
        )
        return cookies.clear()

    @app.post("/auth/password", response_model=UserResponse)
    async def change_password(
        body: PasswordChangeRequest, request: Request
    ) -> Response:
        """Change the password and revoke previous sessions."""
        await authenticated_user(request)
        try:
            result = await run_in_threadpool(
                authentication.change_password,
                request.cookies.get(COOKIE_NAME, ""),
                body.current_password,
                body.new_password,
            )
        except PasswordRejectedError:
            return JSONResponse(
                status_code=400, content={"code": "password_rejected"}
            )
        except RegistrationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return cookies.response(result)


def _public_user(user: User) -> UserResponse:
    """Select public account fields and exclude credential material."""
    return UserResponse(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        email_verified=user.email_verified,
    )


def _logout(authentication: ManageAuthentication, request: Request) -> None:
    """Revoke both cookies' credentials even when the access token expired."""
    authentication.logout(request.cookies.get(COOKIE_NAME, ""))
    authentication.logout_refresh(request.cookies.get(REFRESH_COOKIE_NAME, ""))
