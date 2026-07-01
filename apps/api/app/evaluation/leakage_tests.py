from __future__ import annotations

from app.services.future_data_firewall import FutureDataFirewall


def check_agent_text_for_leakage(text: str) -> dict[str, object]:
    passed, suspected = FutureDataFirewall().inspect_text(text)
    return {"passed": passed, "suspected_terms": suspected}
