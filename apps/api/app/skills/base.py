from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.skills.permissions import PermissionLevel

SkillImplementation = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    permission_level: PermissionLevel
    deterministic: bool
    side_effecting: bool
    allowed_agents: set[str]
    implementation: SkillImplementation
    timeout_ms: int = 1000
    rate_limit: int = 60
