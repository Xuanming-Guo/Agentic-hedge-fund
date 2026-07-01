# Security Policy

Agentic Hedge Fund is simulation-only and must not be connected to real brokerage or real-money trading systems.

## Secrets

- Store secrets only in local `.env` files.
- `.env` is gitignored.
- `.env.example` must never contain secrets.
- Qwen/DashScope API keys are used only by the backend.
- The frontend must never receive API keys.

## Reporting

Please open a private security advisory or contact the maintainers before publishing a vulnerability.

## Safety Boundaries

- Do not add real brokerage integrations.
- Do not add real-money deployment instructions.
- Do not bypass deterministic risk, compliance, broker, or ledger services.
- Do not let LLM output directly mutate state.
