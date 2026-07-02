from __future__ import annotations

from app.scripts.wait_for_db import wait_for_database


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
    assert messages[-1] == "Database is reachable after 3 attempt(s)."


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
        assert "Database did not become reachable within 2s" in str(exc)
        assert "host 'postgres' not known" in str(exc)
    else:
        raise AssertionError("wait_for_database should have timed out")
