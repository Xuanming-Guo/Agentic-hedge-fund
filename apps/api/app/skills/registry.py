from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.observability.metrics import skill_call_failures_total, skill_calls_total
from app.skills.audit import audit_hash
from app.skills.base import Skill
from app.skills.permissions import AGENT_PERMISSIONS, PermissionLevel
from app.skills.schemas import SkillCallRecord, SkillDefinition


class SkillRegistry:
    def __init__(self) -> None:
        self.skills: dict[str, Skill] = {}
        self.calls: list[SkillCallRecord] = []

    def register(self, skill: Skill) -> None:
        self.skills[skill.name] = skill

    def definitions(self) -> list[SkillDefinition]:
        return [
            SkillDefinition(
                name=skill.name,
                description=skill.description,
                permission_level=skill.permission_level,
                deterministic=skill.deterministic,
                side_effecting=skill.side_effecting,
                allowed_agents=sorted(skill.allowed_agents),
                timeout_ms=skill.timeout_ms,
                rate_limit=skill.rate_limit,
            )
            for skill in sorted(self.skills.values(), key=lambda item: item.name)
        ]

    def call(
        self,
        *,
        skill_name: str,
        input_json: dict[str, Any],
        simulation_id: str,
        cycle_id: str | None,
        agent_id: str | None,
        mode: str = "function_calling",
    ) -> SkillCallRecord:
        started = time.perf_counter()
        skill = self.skills[skill_name]
        permission_decision = self._permission_decision(skill, agent_id)
        status = "succeeded"
        output: dict[str, Any] | None = None
        error: dict[str, Any] | None = None
        effective_input = {"simulation_id": simulation_id, **input_json}
        if permission_decision != "allowed":
            status = "denied"
            error = {"message": permission_decision}
            skill_call_failures_total.labels(skill=skill_name).inc()
        else:
            try:
                output = skill.implementation(effective_input)
                skill_calls_total.labels(skill=skill_name).inc()
            except Exception as exc:  # pragma: no cover - defensive audit path
                status = "failed"
                error = {"message": str(exc)}
                skill_call_failures_total.labels(skill=skill_name).inc()
        latency_ms = int((time.perf_counter() - started) * 1000)
        record = SkillCallRecord(
            id=str(uuid4()),
            simulation_id=simulation_id,
            cycle_id=cycle_id,
            agent_id=agent_id,
            skill_name=skill_name,
            mode=mode,  # type: ignore[arg-type]
            input_json=input_json,
            output_json=output,
            status=status,  # type: ignore[arg-type]
            permission_decision=permission_decision,
            latency_ms=latency_ms,
            error_json=error,
            audit_hash=audit_hash(
                {"skill": skill_name, "input": input_json, "output": output, "error": error}
            ),
            completed_at=datetime.utcnow(),
        )
        self.calls.append(record)
        return record

    def _permission_decision(self, skill: Skill, agent_id: str | None) -> str:
        if agent_id is None:
            return "allowed"
        if agent_id not in skill.allowed_agents:
            return f"denied: {agent_id} is not allowed to call {skill.name}"
        if skill.permission_level not in AGENT_PERMISSIONS.get(agent_id, set()):
            return f"denied: missing permission {skill.permission_level}"
        if skill.side_effecting and skill.permission_level == PermissionLevel.ROUTE_APPROVED_ORDER:
            return "allowed"
        return "allowed"
