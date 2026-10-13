"""Database-backed fixed-window counters shared by all API workers."""

import hashlib
import hmac
from collections.abc import Callable
from time import time

from sqlalchemy import case, delete

from harass.application.ports.request_limiter import RequestLimiter
from harass.infrastructure.persistence.sqlalchemy_stores import SessionFactory
from harass.infrastructure.persistence.tables import RequestLimitRow
from harass.infrastructure.persistence.upsert import insert_for


class SqlAlchemyRequestLimiter(RequestLimiter):
    """Store one keyed counter per client and operation with atomic conflict updates."""

    def __init__(
        self, session_factory: SessionFactory, secret: str, clock: Callable[[], float] = time
    ) -> None:
        """Retain a private identifier key and the clock used for fixed windows."""
        self._session_factory = session_factory
        self._secret = secret.encode("utf-8")
        self._clock = clock

    def consume(self, key: str, limit: int, window_seconds: int = 60) -> int:
        """Admit at most limit requests within the shared fixed window."""
        if limit < 1 or window_seconds < 1:
            raise ValueError("Request limits and windows must be positive.")
        now = int(self._clock())
        start = now - now % window_seconds
        digest = hmac.new(self._secret, key.encode("utf-8"), hashlib.sha256).hexdigest()
        with self._session_factory() as session, session.begin():
            session.execute(
                delete(RequestLimitRow).where(RequestLimitRow.window_start < start - 86400)
            )
            statement = insert_for(session, RequestLimitRow).values(
                bucket_key=digest, window_start=start, request_count=1
            )
            count = session.scalar(
                statement.on_conflict_do_update(
                    index_elements=["bucket_key"],
                    set_={
                        "window_start": start,
                        "request_count": case(
                            (RequestLimitRow.window_start != start, 1),
                            else_=RequestLimitRow.request_count + 1,
                        ),
                    },
                ).returning(RequestLimitRow.request_count)
            )
        return 0 if count is not None and count <= limit else start + window_seconds - now
