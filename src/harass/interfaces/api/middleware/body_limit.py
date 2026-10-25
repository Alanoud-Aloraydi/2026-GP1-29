"""Bound incoming request bodies before JSON parsing or password work."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimit:
    """Bound request bodies, including chunked uploads."""

    def __init__(self, app: ASGIApp, max_bytes: int = 65536) -> None:
        """Bind the downstream application and a positive byte limit."""
        if max_bytes < 1:
            raise ValueError("Request body limit must be positive.")
        self.app, self.max_bytes = app, max_bytes

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Reject oversized bodies before application handlers run."""
        if scope["type"] != "http" or scope["method"] not in {
            "POST",
            "PUT",
            "PATCH",
        }:
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                await JSONResponse(
                    {"detail": "Request body is too large."}, status_code=413
                )(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            """Deliver the bounded request body to downstream handlers once."""
            nonlocal replayed
            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, replay, send)
