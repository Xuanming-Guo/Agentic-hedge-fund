from __future__ import annotations

from typing import Any

from app.skills.registry import SkillRegistry
from app.skills.schemas import SkillCallRecord


class QwenToolGateway:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def execute_tool_calls(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        simulation_id: str,
        cycle_id: str,
        agent_id: str,
    ) -> list[SkillCallRecord]:
        records: list[SkillCallRecord] = []
        for call in tool_calls:
            records.append(
                self.registry.call(
                    skill_name=call["name"],
                    input_json=call.get("arguments", {}),
                    simulation_id=simulation_id,
                    cycle_id=cycle_id,
                    agent_id=agent_id,
                    mode="function_calling",
                )
            )
        return records
