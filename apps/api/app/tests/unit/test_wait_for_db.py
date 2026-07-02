from __future__ import annotations

from app.scripts.wait_for_db import database_target, wait_for_database


def test_database_target_redacts_credentials_and_reports_postgres_host() -> None:
    assert (
        database_target("postgresql+psycopg://postgres:secret@postgres:5432/agentic_hedge_fund")
        == "postgres:5432/agentic_hedge_fund"
    )


def test_wait_for_database_retries_until_reachable() -> None:
    calls = 0
    now = 0.0
    messages: list[str] = []

    def check(_: str) -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("host 'postgres' not known")

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    attempts = wait_for_database(
        database_url="postgresql+psycopg://postgres:postgres@postgres:5432/db",
        timeout_seconds=10,
        interval_seconds=1,
        check=check,
        sleep=sleep,
        monotonic=monotonic,
        log=messages.append,
    )

    assert attempts == 3
    assert calls == 3
    assert messages[0] == "Waiting for database at postgres:5432/db."
    assert messages[-1] == "Database is reachable at postgres:5432/db after 3 attempt(s)."
    assert any("docker compose down --remove-orphans" in message for message in messages)


def test_wait_for_database_times_out_with_clear_error() -> None:
    now = 0.0

    def check(_: str) -> None:
        raise OSError("host 'postgres' not known")

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    try:
        wait_for_database(
            database_url="postgresql+psycopg://postgres:postgres@postgres:5432/db",
            timeout_seconds=2,
            interval_seconds=1,
            check=check,
            sleep=sleep,
            monotonic=monotonic,
            log=lambda _: None,
        )
    except TimeoutError as exc:
        assert "Database at postgres:5432/db did not become reachable within 2s" in str(exc)
        assert "host 'postgres' not known" in str(exc)
    else:
        raise AssertionError("wait_for_database should have timed out")
