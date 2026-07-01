from __future__ import annotations

from app.skills.registry import SkillRegistry
from app.skills.schemas import SkillCallRecord


class LocalMCPAdapter:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict,
        simulation_id: str,
        cycle_id: str | None,
        agent_id: str | None,
    ) -> SkillCallRecord:
        return self.registry.call(
            skill_name=tool_name,
            input_json=arguments,
            simulation_id=simulation_id,
            cycle_id=cycle_id,
            agent_id=agent_id,
            mode="mcp",
        )
