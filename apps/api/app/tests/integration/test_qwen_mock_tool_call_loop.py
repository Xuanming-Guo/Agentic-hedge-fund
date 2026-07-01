from __future__ import annotations

from app.services.simulation_engine import SimulationEngine


def test_mock_agent_cycle_logs_tool_calls() -> None:
    engine = SimulationEngine()
    state = engine.create_simulation("2024-05-10")
    for _ in range(7):
        engine.tick(state)
    assert engine.registry.calls
    assert any(call.skill_name == "market_get_snapshot" for call in engine.registry.calls)
