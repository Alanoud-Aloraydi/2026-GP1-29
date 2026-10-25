"""Resolve account ownership from signed, revocable session cookies."""

from typing import cast

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from harass.application.accounts.authentication import ManageAuthentication
from harass.application.accounts.errors import AuthenticationError
from harass.domain.authentication import User
from harass.interfaces.api.accounts.cookies import (
    COOKIE_NAME,
)


async def authenticated_owner(request: Request) -> str:
    """Resolve ownership exclusively from a valid authenticated cookie."""
    user = await authenticated_user(request)
    return user.user_id


async def authenticated_user(request: Request) -> User:
    """Resolve a live account through a signed revocable cookie."""
    authentication = cast(
        ManageAuthentication | None,
        getattr(request.app.state, "authentication", None),
    )
    token = request.cookies.get(COOKIE_NAME)
    if authentication is None or token is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        return await run_in_threadpool(authentication.authenticate, token)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=401, detail="Session is invalid or expired."
        ) from error
