from __future__ import annotations

from app.skills.base import Skill
from app.skills.permissions import PermissionLevel
from app.skills.qwen_tool_adapter import QwenToolGateway
from app.skills.registry import SkillRegistry


def test_qwen_tool_gateway_executes_registered_tool() -> None:
    registry = SkillRegistry()
    registry.register(
        Skill(
            name="market_get_snapshot",
            description="read",
            permission_level=PermissionLevel.READ_MARKET,
            deterministic=True,
            side_effecting=False,
            allowed_agents={"MacroAnalystAgent"},
            implementation=lambda data: {"prices": {"ALPH": 120}},
        )
    )
    records = QwenToolGateway(registry).execute_tool_calls(
        tool_calls=[{"name": "market_get_snapshot", "arguments": {}}],
        simulation_id="sim",
        cycle_id="cycle",
        agent_id="MacroAnalystAgent",
    )
    assert records[0].status == "succeeded"
    assert records[0].mode == "function_calling"
