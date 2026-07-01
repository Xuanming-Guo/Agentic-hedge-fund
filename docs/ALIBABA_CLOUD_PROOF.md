# Alibaba Cloud Proof

Agentic Hedge Fund uses Qwen Cloud through an OpenAI-compatible provider.

Proof files:

- Qwen API usage: `apps/api/app/agents/qwen_client.py`
- Qwen model routing: `apps/api/app/agents/model_router.py`
- Custom skills and function-calling gateway: `apps/api/app/skills/qwen_tool_adapter.py`
- Local MCP configuration: `configs/mcp.local.json`

The backend can run on Alibaba Cloud ECS with Docker Compose and a local Postgres container.

Proof video checklist:

1. Show ECS instance or Alibaba Cloud terminal.
2. Run `docker compose ps`.
3. Open `/health`.
4. Open `/api/proof/qwen`.
5. Open dashboard connected to backend.
6. Trigger a Qwen or mock agent run.
7. Show a Qwen tool call.
8. Show MCP tool graph.
9. Show benchmark result.
