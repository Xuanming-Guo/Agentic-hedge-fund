from __future__ import annotations

import json
import sys

MCP_SERVERS = {
    "mcp-market-data": [
        "get_market_snapshot",
        "get_released_events",
        "get_orderbook_depth",
        "get_recent_trade_tape",
    ],
    "mcp-portfolio-risk": [
        "get_portfolio_state",
        "run_pre_trade_risk_check",
        "estimate_market_impact",
    ],
    "mcp-compliance": ["run_compliance_check", "check_future_data_reference", "write_audit_note"],
    "mcp-benchmark": ["run_benchmark", "get_benchmark_results", "compute_agent_society_advantage"],
    "mcp-trading-actions": ["validate_order_plan", "route_approved_order"],
}


def smoke() -> dict[str, object]:
    return {"ok": True, "servers": MCP_SERVERS, "side_effecting_enabled_by_default": False}


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        print(json.dumps(smoke(), indent=2))
