from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_INTERVAL_SECONDS = 2.0
DNS_HINT_ATTEMPTS = {2, 3, 6}


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
    target = database_target(url)
    deadline = monotonic() + timeout_seconds
    attempts = 0
    last_error: Exception | None = None
    log(f"Waiting for database at {target}.")

    while monotonic() <= deadline:
        attempts += 1
        try:
            check(url)
        except Exception as exc:
            last_error = exc
            log(f"Waiting for database ({attempts}): {exc.__class__.__name__}: {exc}")
            if attempts in DNS_HINT_ATTEMPTS and _looks_like_dns_error(exc):
                log(
                    "Database hostname still cannot be resolved. Check that docker compose "
                    "created one project network for api and postgres; try "
                    "`docker compose down --remove-orphans` then `docker compose up --build`. "
                    "If testing multiple clones at once, use a unique project name such as "
                    "`docker compose -p ahf-clean up --build`."
                )
            sleep(interval_seconds)
            continue

        log(f"Database is reachable at {target} after {attempts} attempt(s).")
        return attempts

    detail = f"{last_error.__class__.__name__}: {last_error}" if last_error else "timed out"
    raise TimeoutError(
        f"Database at {target} did not become reachable within "
        f"{timeout_seconds:.0f}s ({detail})."
    )


def database_target(database_url: str) -> str:
    try:
        url = make_url(database_url)
    except Exception:
        return "configured DATABASE_URL"

    host = url.host or "localhost"
    port = f":{url.port}" if url.port else ""
    database = f"/{url.database}" if url.database else ""
    return f"{host}{port}{database}"


def _looks_like_dns_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "failed to resolve host" in text
        or "could not translate host name" in text
        or "name or service not known" in text
        or "not known" in text
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
