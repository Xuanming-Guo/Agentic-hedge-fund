# Agent Protocol

Agents operate in a formal decision cycle:

1. Coordinator decomposes the task.
2. Macro, fundamental, technical, and sentiment analysts produce signal reports.
3. Bull and bear researchers debate.
4. Research manager synthesizes.
5. Portfolio manager proposes.
6. Risk manager requests deterministic risk checks.
7. Compliance officer requests deterministic evidence and leakage checks.
8. Investment committee chair resolves conflicts.
9. Execution trader creates an order plan.
10. Broker validates and routes only approved simulation orders.

All Qwen-facing outputs are strict JSON and validated with Pydantic schemas in `apps/api/app/schemas/agent_outputs.py`.

Prompts require concise rationale, evidence IDs, uncertainty, and no chain-of-thought. Invalid output cannot place orders.

Runtime cycles route analyst, debate, and portfolio-manager outputs through the configured `LLMProvider`.
The default mock provider is deterministic, but it uses the same context packer, model router, JSON schemas,
Qwen tool gateway, MCP-mode portfolio call, and audit log path as Qwen mode.
