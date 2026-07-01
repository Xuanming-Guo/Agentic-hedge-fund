from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.skills.permissions import PermissionLevel


class SkillDefinition(BaseModel):
    name: str
    description: str
    permission_level: PermissionLevel
    deterministic: bool
    side_effecting: bool
    allowed_agents: list[str]
    timeout_ms: int = 1000
    rate_limit: int = 60


class SkillCallRecord(BaseModel):
    id: str
    simulation_id: str
    cycle_id: str | None = None
    agent_id: str | None = None
    skill_name: str
    mode: Literal["function_calling", "mcp", "internal"]
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None = None
    status: Literal["succeeded", "failed", "denied"]
    permission_decision: str
    latency_ms: int
    error_json: dict[str, Any] | None = None
    audit_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
