from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass(slots=True)
class HumanApprovalRequest:
    id: str
    simulation_id: str
    cycle_id: str
    reason: str
    status: str
    requested_at_sim_time: datetime
    resolution_json: dict | None = None


@dataclass
class HumanApprovalService:
    requests: dict[str, HumanApprovalRequest] = field(default_factory=dict)

    def request(
        self, simulation_id: str, cycle_id: str, reason: str, timestamp: datetime
    ) -> HumanApprovalRequest:
        item = HumanApprovalRequest(
            id=str(uuid4()),
            simulation_id=simulation_id,
            cycle_id=cycle_id,
            reason=reason,
            status="pending",
            requested_at_sim_time=timestamp,
        )
        self.requests[item.id] = item
        return item

    def resolve(
        self, request_id: str, status: str, resolution_json: dict | None = None
    ) -> HumanApprovalRequest:
        item = self.requests[request_id]
        item.status = status
        item.resolution_json = resolution_json or {}
        return item

    def list_for_simulation(self, simulation_id: str) -> list[HumanApprovalRequest]:
        return [item for item in self.requests.values() if item.simulation_id == simulation_id]
