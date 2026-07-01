from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_qwen_proof_endpoint_redacts_provider_details() -> None:
    client = TestClient(app)

    response = client.get("/api/proof/qwen")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["provider_configured"], bool)
    assert isinstance(payload["json_mode_enabled"], bool)
    assert payload["function_calling_enabled"] is True
    assert payload["mcp_enabled"] is True
    assert payload["tool_gateway_configured"] is True
    assert payload["mcp_configured"] is True
    assert "provider" not in payload
    assert "effective_provider" not in payload
    assert "configured_provider" not in payload
    assert "provider_precedence" not in payload
    assert "last_llm_model" not in payload
    assert "active_provider_file" not in payload
