from __future__ import annotations

from datetime import UTC, datetime

from app.services.human_approval_service import HumanApprovalService


def test_human_approval_flow() -> None:
    service = HumanApprovalService()
    request = service.request("sim", "cycle", "large order", datetime.now(UTC))
    assert request.status == "pending"
    resolved = service.resolve(request.id, "approved")
    assert resolved.status == "approved"
