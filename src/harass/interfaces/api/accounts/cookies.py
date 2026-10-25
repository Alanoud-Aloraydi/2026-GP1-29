"""Transport access and refresh credentials in HTTP-only cookies."""

from datetime import UTC, datetime

from fastapi import Response
from fastapi.responses import JSONResponse

from harass.domain.authentication import AuthenticatedLogin

COOKIE_NAME = "harass_session"
REFRESH_COOKIE_NAME = "harass_refresh"


class SessionCookies:
    """Use consistent attributes when setting and clearing cookies."""

    def __init__(self, secure: bool, access_seconds: int) -> None:
        """Bind transport security and the bounded access lifetime."""
        self._secure, self._access_seconds = secure, access_seconds

    def response(self, login: AuthenticatedLogin) -> JSONResponse:
        """Return public account fields and set credential cookies."""
        response = JSONResponse(
            content={
                "user_id": login.user.user_id,
                "full_name": login.user.full_name,
                "email": login.user.email,
                "email_verified": login.user.email_verified,
            }
        )
        self._set(
            response, COOKIE_NAME, login.token, self._access_seconds, "/"
        )
        if login.refresh_token and login.refresh_expires_at:
            remaining = max(
                0,
                int(
                    (
                        login.refresh_expires_at - datetime.now(UTC)
                    ).total_seconds()
                ),
            )
            self._set(
                response,
                REFRESH_COOKIE_NAME,
                login.refresh_token,
                remaining,
                "/auth",
            )
        return response

    def clear(self, status: int = 204) -> Response:
        """Expire both cookies with the same paths used when setting them."""
        response = Response(status_code=status)
        for name, path in ((COOKIE_NAME, "/"), (REFRESH_COOKIE_NAME, "/auth")):
            response.delete_cookie(
                name,
                path=path,
                secure=self._secure,
                httponly=True,
                samesite="strict",
            )
        return response

    def _set(
        self,
        response: Response,
        name: str,
        value: str,
        seconds: int,
        path: str,
    ) -> None:
        """Set a strict same-site, HTTP-only credential cookie."""
        response.set_cookie(
            name,
            value,
            max_age=seconds,
            secure=self._secure,
            httponly=True,
            samesite="strict",
            path=path,
        )
