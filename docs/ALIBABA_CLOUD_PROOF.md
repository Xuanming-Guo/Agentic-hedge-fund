# Alibaba Cloud Proof

Agentic Hedge Fund uses Qwen Cloud through an OpenAI-compatible provider.

Proof files:

- Qwen API usage: `apps/api/app/agents/qwen_client.py` https://github.com/Xuanming-Guo/Agentic-hedge-fund/blob/main/apps/api/app/agents/qwen_client.py
- Qwen model routing: `apps/api/app/agents/model_router.py` https://github.com/Xuanming-Guo/Agentic-hedge-fund/blob/main/apps/api/app/agents/model_router.py
- Custom skills and function-calling gateway: `apps/api/app/skills/qwen_tool_adapter.py` https://github.com/Xuanming-Guo/Agentic-hedge-fund/blob/main/apps/api/app/skills/qwen_tool_adapter.py
- Local MCP configuration: `configs/mcp.local.json` https://github.com/Xuanming-Guo/Agentic-hedge-fund/blob/main/configs/mcp.local.json

The backend can run on Alibaba Cloud ECS with Docker Compose and a local Postgres container.
