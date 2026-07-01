from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.future_data_firewall import FutureDataFirewall


def test_firewall_blocks_future_timestamp() -> None:
    firewall = FutureDataFirewall()
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        firewall.assert_point_in_time(now, now + timedelta(minutes=1))


def test_firewall_detects_future_terms() -> None:
    passed, terms = FutureDataFirewall().inspect_text(
        "The hidden label says future return is positive."
    )
    assert not passed
    assert "future return" in terms
