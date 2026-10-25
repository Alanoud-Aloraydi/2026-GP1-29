"""Feature-gated account-email routes with generic delivery acknowledgments."""

import logging
from collections.abc import Callable

from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from harass.application.accounts.errors import (
    InvalidAccountActionError,
    PasswordRejectedError,
)
from harass.application.accounts.recovery import AccountRecovery
from harass.interfaces.api.accounts.cookies import SessionCookies
from harass.interfaces.api.accounts.dependencies import authenticated_user
from harass.interfaces.api.accounts.recovery_schemas import (
    AccountTokenRequest,
    PasswordResetRequest,
    RecoveryEmailRequest,
)

logger = logging.getLogger(__name__)


def install_recovery_routes(
    app: FastAPI, recovery: AccountRecovery | None, cookies: SessionCookies
) -> None:
    """Expose availability and register action routes only when enabled."""

    @app.get("/auth/features")
    def features() -> dict[str, bool]:
        """Reveal availability without exposing provider settings."""
        return {"account_email_enabled": recovery is not None}

    if recovery is None:
        return
    service = recovery

    @app.exception_handler(InvalidAccountActionError)
    async def invalid_action(
        _: Request, error: InvalidAccountActionError
    ) -> JSONResponse:
        """Keep expired, invalid and consumed token failures identical."""
        return JSONResponse(
            status_code=400, content={"code": "account_link_invalid"}
        )

    @app.post("/auth/password/forgot", status_code=202)
    def forgot_password(
        body: RecoveryEmailRequest, background: BackgroundTasks
    ) -> dict[str, str]:
        """Acknowledge requests before account lookup or mail delivery."""
        background.add_task(_deliver, service.request_reset, body.email)
        return {"status": "accepted"}

    @app.post("/auth/email/request-verification", status_code=202)
    async def request_verification(
        request: Request, background: BackgroundTasks
    ) -> dict[str, str]:
        """Deliver only to the authenticated account's registered email."""
        user = await authenticated_user(request)
        background.add_task(
            _deliver, service.request_verification, user.user_id
        )
        return {"status": "accepted"}

    @app.post("/auth/email/verify", status_code=204)
    async def verify_email(body: AccountTokenRequest) -> Response:
        """Consume verification without creating an authentication session."""
        await run_in_threadpool(service.verify, body.token)
        return Response(status_code=204)

    @app.post("/auth/password/reset", status_code=204)
    async def reset_password(body: PasswordResetRequest) -> Response:
        """Change the password and require a subsequent explicit login."""
        try:
            await run_in_threadpool(
                service.reset, body.token, body.new_password
            )
        except PasswordRejectedError:
            return JSONResponse(
                status_code=400, content={"code": "password_rejected"}
            )
        return cookies.clear()


def _deliver(callback: Callable[[str], None], identifier: str) -> None:
    """Contain delivery failures without logging email addresses or tokens."""
    try:
        callback(identifier)
    except Exception as error:
        logger.error("Account mail delivery failed: %s", type(error).__name__)
