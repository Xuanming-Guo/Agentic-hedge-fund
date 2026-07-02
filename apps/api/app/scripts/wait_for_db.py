from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable

from sqlalchemy import create_engine, text

from app.core.config import get_settings

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_INTERVAL_SECONDS = 2.0


def check_database(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def wait_for_database(
    *,
    database_url: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    check: Callable[[str], None] = check_database,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = print,
) -> int:
    url = database_url or get_settings().database_url
    deadline = monotonic() + timeout_seconds
    attempts = 0
    last_error: Exception | None = None

    while monotonic() <= deadline:
        attempts += 1
        try:
            check(url)
        except Exception as exc:
            last_error = exc
            log(f"Waiting for database ({attempts}): {exc.__class__.__name__}: {exc}")
            sleep(interval_seconds)
            continue

        log(f"Database is reachable after {attempts} attempt(s).")
        return attempts

    detail = f"{last_error.__class__.__name__}: {last_error}" if last_error else "timed out"
    raise TimeoutError(
        f"Database did not become reachable within {timeout_seconds:.0f}s ({detail})."
    )


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def main() -> None:
    timeout_seconds = _env_float("WAIT_FOR_DB_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    interval_seconds = _env_float("WAIT_FOR_DB_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)
    try:
        wait_for_database(timeout_seconds=timeout_seconds, interval_seconds=interval_seconds)
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
