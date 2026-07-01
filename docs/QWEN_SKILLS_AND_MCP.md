# Qwen Skills And MCP

The Qwen Tool Gateway exposes deterministic platform capabilities as permissioned skills.

Representative skills:

- `market_get_snapshot`
- `news_get_released_events`
- `portfolio_get_state`
- `orderbook_get_depth`
- `research_compute_indicators`
- `exchange_estimate_market_impact`
- `risk_pre_trade_check`
- `compliance_pre_trade_check`
- `broker_validate_order_plan`
- `broker_route_approved_order`
- `benchmark_compare_modes`
- `audit_write_decision`

Every skill call is logged with input, output, permission decision, latency, mode, side-effecting flag, and audit hash.

Local MCP servers live in `apps/api/app/mcp_servers`. Run:

```bash
make mcp-smoke
```
