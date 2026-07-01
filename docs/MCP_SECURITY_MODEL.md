# MCP Security Model

Local MCP servers are for local demo and judging proof only.

Rules:

- MCP servers run locally.
- Do not expose MCP servers publicly.
- Tool descriptions are short and explicit.
- Tool outputs are sanitized before returning to agents.
- Side-effecting trading actions are disabled by default.
- Routing requires an approval token and remains simulation-only.
- All MCP and function-calling skill calls are logged.
