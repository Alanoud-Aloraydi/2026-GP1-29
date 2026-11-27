"""Bounded health probes for the HTTP process and durable worker heartbeat."""

import os
import sys
from urllib.request import urlopen

from sqlalchemy import create_engine, text

from harass.bootstrap.database import DEFAULT_API_PORT, judge_slot


def healthy(service: str) -> bool:
    """Check service liveness without submitting target or judge requests."""
    if service == "api":
        port = os.environ.get("HARASS_API_PORT", DEFAULT_API_PORT)
        with urlopen(f"http://127.0.0.1:{port}/auth/features", timeout=3) as response:
            return bool(response.status == 200)
    if service != "worker":
        return False
    engine = create_engine(os.environ["HARASS_DATABASE_URL"], connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            return bool(
                connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM worker_presence "
                        "WHERE slot_key = :slot "
                        "AND last_seen > now() - interval '60 seconds')"
                    ),
                    {"slot": judge_slot(os.environ["HARASS_JUDGE_SERVER_URL"])},
                )
            )
    finally:
        engine.dispose()


def main() -> None:
    """Return a health-check status without exposing provider exceptions."""
    try:
        status = len(sys.argv) == 2 and healthy(sys.argv[1])
    except Exception:
        status = False
    raise SystemExit(0 if status else 1)


if __name__ == "__main__":
    main()
