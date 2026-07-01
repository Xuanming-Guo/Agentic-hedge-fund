from __future__ import annotations

from app.skills.base import Skill
from app.skills.permissions import PermissionLevel
from app.skills.registry import SkillRegistry


def test_skill_permission_allows_authorized_agent() -> None:
    registry = SkillRegistry()
    registry.register(
        Skill(
            name="market_get_snapshot",
            description="read market",
            permission_level=PermissionLevel.READ_MARKET,
            deterministic=True,
            side_effecting=False,
            allowed_agents={"MacroAnalystAgent"},
            implementation=lambda data: {"ok": True, "simulation_id": data["simulation_id"]},
        )
    )
    record = registry.call(
        skill_name="market_get_snapshot",
        input_json={},
        simulation_id="sim",
        cycle_id="cycle",
        agent_id="MacroAnalystAgent",
    )
    assert record.status == "succeeded"
    assert record.output_json == {"ok": True, "simulation_id": "sim"}


def test_skill_permission_denies_wrong_agent() -> None:
    registry = SkillRegistry()
    registry.register(
        Skill(
            name="risk_pre_trade_check",
            description="risk",
            permission_level=PermissionLevel.REQUEST_RISK_CHECK,
            deterministic=True,
            side_effecting=False,
            allowed_agents={"RiskManagerAgent"},
            implementation=lambda data: {"ok": True},
        )
    )
    record = registry.call(
        skill_name="risk_pre_trade_check",
        input_json={},
        simulation_id="sim",
        cycle_id="cycle",
        agent_id="PortfolioManagerAgent",
    )
    assert record.status == "denied"
    assert "denied" in record.permission_decision
