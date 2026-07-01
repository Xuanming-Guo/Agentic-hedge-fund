# Architecture

Agentic Hedge Fund is a simulation-only multi-agent market-risk lab.

```mermaid
flowchart TB
  Dashboard[React Dashboard] --> API[FastAPI API]
  API --> Sim[Simulation Engine]
  API --> WS[WebSocket Broadcaster]
  Sim --> Data[Market Data + Event Service]
  Sim --> Agents[Agent Orchestrator]
  Agents --> LLM[QwenCloudProvider or MockLLMProvider]
  Agents --> Skills[Qwen Tool Gateway]
  Skills --> MCP[Local MCP Servers]
  Skills --> Risk[Risk Service]
  Skills --> Compliance[Compliance Service]
  Skills --> Broker[Broker Service]
  Broker --> Exchange[Limit Order Book Exchange]
  Exchange --> Ledger[Bank/Treasury/Ledger]
  API --> Bench[Benchmark Engine]
  API --> DB[(PostgreSQL)]
```

## Service Boundaries

- Agents propose, debate, and explain.
- Risk, compliance, broker, exchange, and ledger services enforce state.
- Provider output is validated before it influences simulated orders.
- The frontend receives only API and WebSocket data, never secrets.

## Determinism

Mock mode is deterministic for tests and demos. Synthetic data is generated from scenario seeds. Agents only receive current and historical bars/events.
