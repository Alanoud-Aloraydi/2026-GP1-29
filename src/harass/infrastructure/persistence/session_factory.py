"""Type contract for independent SQLAlchemy database sessions."""

from collections.abc import Callable

from sqlalchemy.orm import Session

type SessionFactory = Callable[[], Session]
