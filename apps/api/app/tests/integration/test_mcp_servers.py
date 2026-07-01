from __future__ import annotations

from app.mcp_servers.common import smoke


def test_mcp_smoke_lists_servers() -> None:
    result = smoke()
    assert result["ok"] is True
    assert "mcp-market-data" in result["servers"]
