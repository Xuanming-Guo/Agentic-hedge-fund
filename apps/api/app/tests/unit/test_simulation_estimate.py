from __future__ import annotations

from types import SimpleNamespace

from app.api import routes


def test_simulation_estimate_adds_ten_minute_fixed_buffer(monkeypatch) -> None:
    monkeypatch.setattr(routes, "ENGINE", SimpleNamespace(active_llm_provider="qwen"))

    estimate = routes._estimate_for(30)

    assert estimate.expected_agent_cycles == 2
    assert estimate.expected_llm_calls == 12
    assert estimate.estimated_real_seconds == 661
