# Agentic Hedge Fund

**A Qwen Cloud Agent Society that runs a simulated hedge-fund trading desk.**

Agentic Hedge Fund is a replay market simulation where specialized Qwen agents decompose a trading day, debate catalysts, route a basket through portfolio/risk/compliance/committee gates, execute simulated fills, and benchmark the agent society against a required `single_agent` baseline.

This is a simulation and education project only. It does not connect to a real brokerage, does not execute real trades, and does not provide investment advice.

## Hackathon Track

Qwen Cloud Global AI Hackathon - **Track 3: Agent Society**.

## What The Demo Shows

- A dockable trading dashboard with market replay candles, order book, portfolio, and optional agent/governance panels.
- An already simulated full-day replay named **`Example Full Day Simulation 11th June 2025`** so reviewers can open a realistic saved run immediately after cloning.
- Qwen agents evaluating up to 10 tickers as a portfolio slate.
- Evidence-led allocation roles: primary catalyst, hedge candidate, relative-value candidate, and watchlist/hold reasons.
- Simulated long/short marketable IOC fills through a deterministic order book and ledger.
- Agent chat details with formatted structured JSON, tool calls, validation notes, and state transitions.
- Replay keyframes for fast loading of full-day recordings.
- Agent Society benchmark proof: `multi_agent` vs `single_agent`.

## Architecture

```mermaid
flowchart TB
  User["Reviewer / trader browser"]

  subgraph Alibaba["Alibaba Cloud / Docker Runtime"]
    ECS["Alibaba ECS host or local Docker host"]
    Compose["docker compose: web + api + postgres"]
    APIContainer["FastAPI container"]
    WebContainer["React/Vite web container"]
    Postgres[("PostgreSQL")]
    RecVolume[("simulation-recordings volume")]
    Env["DASHSCOPE_API_KEY server-side only"]
    ProofDocs["infra/alibaba + docs/ALIBABA_CLOUD_PROOF.md"]
  end

  subgraph Frontend["Frontend Trading Cockpit"]
    Web["React dashboard shell"]
    Controls["Start / pause / resume / step / speed / stop-save"]
    SimModal["Simulations modal and replay picker"]
    Candles["Market Replay Candles"]
    OrderBookPanel["Order Book panel"]
    PortfolioPanel["Portfolio panel: cash, positions, PnL, exposure, fills"]
    AgentLive["Agent Society Live"]
    Workbench["Agent Workbench: states, decisions, debate"]
    CandidatePanel["Candidate Slate"]
    ReleasedEvents["Released Events"]
    RuntimePanel["Agent Runtime"]
    CommitteePanel["Investment Committee"]
    BenchmarkPanel["Agent Society Benchmark: multi_agent vs single_agent"]
    DecisionFlow["Agent Decision Flow"]
  end

  subgraph API["FastAPI Public API"]
    Rest["REST controls and replay endpoints"]
    WS["WebSocket snapshots"]
    QwenProof["/api/proof/qwen"]
    MCPStatus["/api/mcp/status"]
    SkillCalls["/api/skills/calls"]
    ReplayAPI["/api/recordings: list, keyframes, frames, resume"]
    BenchAPI["/api/simulations/{id}/benchmark and /api/recordings/{id}/benchmark"]
  end

  subgraph Core["Simulation Core"]
    Engine["Simulation Engine"]
    MarketBundle["Market data bundle: synthetic, yfinance, Alpaca optional"]
    EventClock["Point-in-time event release clock"]
    Slate["Candidate slate: rank, role, hold reason, sector exposure"]
    Recorder["Recording service: manifest, frames.ndjson, keyframes"]
    FixtureSeed["Bundled replay fixture: Example Full Day Simulation 11th June 2025"]
    Bench["Benchmark engine and ASAI"]
  end

  subgraph Society["Qwen Agent Society"]
    Router["Qwen model router"]
    Qwen["Qwen Cloud structured JSON API"]
    Mock["Deterministic mock fallback"]
    Coordinator["CoordinatorAgent"]
    Macro["MacroAnalystAgent"]
    Technical["TechnicalAnalystAgent"]
    Sentiment["SentimentNewsAnalystAgent"]
    Bull["BullResearcherAgent"]
    Bear["BearResearcherAgent"]
    ResearchMgr["ResearchManagerAgent"]
    PM["PortfolioManagerAgent"]
    RiskAgent["RiskManagerAgent"]
    ComplianceAgent["ComplianceOfficerAgent"]
    Chair["InvestmentCommitteeChairAgent"]
    Trader["ExecutionTraderAgent"]
    Narrator["DemoNarratorAgent"]
  end

  subgraph Tools["Tool Gateway + MCP"]
    Gateway["Qwen Tool Gateway"]
    MCP["Local MCP servers"]
    MarketSkill["market data + released events"]
    OrderBookSkill["orderbook depth + imbalance"]
    PortfolioSkill["portfolio, exposure, PnL"]
    RiskSkill["risk limits and sizing"]
    ComplianceSkill["evidence relevance + future-data firewall"]
    BrokerSkill["broker validation and route approval"]
    BenchmarkSkill["benchmark and ablation tools"]
  end

  subgraph Governance["Governance + Execution"]
    RiskSvc["RiskService: resize or reject"]
    ComplianceSvc["ComplianceService: evidence and leakage checks"]
    CommitteeSvc["InvestmentCommitteeService: approve, resize, defer, reject"]
    BrokerSvc["BrokerService: accepted or rejected route"]
    IOC["Marketable IOC child order"]
    Exchange["Deterministic limit-order-book exchange"]
    Sweep["Sweep visible asks for buys or bids for sells"]
    Fill["filled / partially_filled / unfilled"]
    Ledger["PortfolioLedger"]
    LongShort["Buy opens/increases long or covers short; sell reduces/closes long or opens/increases short"]
    PortfolioState["Cash, equity, positions, realized PnL, unrealized PnL, gross/net exposure"]
  end

  User --> WebContainer --> Web
  ECS --> Compose
  Compose --> APIContainer
  Compose --> WebContainer
  Compose --> Postgres
  Compose --> RecVolume
  Env --> APIContainer
  ProofDocs --> ECS

  Web --> Controls
  Web --> SimModal
  Web --> Candles
  Web --> OrderBookPanel
  Web --> PortfolioPanel
  Web --> AgentLive
  Web --> Workbench
  Web --> CandidatePanel
  Web --> ReleasedEvents
  Web --> RuntimePanel
  Web --> CommitteePanel
  Web --> BenchmarkPanel
  Web --> DecisionFlow

  Controls -- "REST" --> Rest
  SimModal -- "replay open / resume" --> ReplayAPI
  Web -- "WebSocket snapshots" --> WS
  BenchmarkPanel -- "run benchmark" --> BenchAPI
  RuntimePanel --> QwenProof
  Workbench --> SkillCalls
  AgentLive --> SkillCalls

  Rest --> Engine
  WS --> Engine
  ReplayAPI --> Recorder
  BenchAPI --> Bench
  QwenProof --> Qwen
  MCPStatus --> MCP
  SkillCalls --> Gateway
  Engine --> MarketBundle
  Engine --> EventClock
  Engine --> Slate
  Engine --> Recorder
  FixtureSeed --> Recorder
  Recorder --> RecVolume
  Engine --> Postgres

  Engine --> Coordinator --> Slate
  Slate --> Macro
  Slate --> Technical
  Slate --> Sentiment
  Macro --> ResearchMgr
  Technical --> ResearchMgr
  Sentiment --> ResearchMgr
  Bull --> ResearchMgr
  Bear --> ResearchMgr
  ResearchMgr --> PM
  PM --> RiskAgent --> ComplianceAgent --> Chair --> Trader
  Narrator --> BenchmarkPanel

  Coordinator --> Router
  Macro --> Router
  Technical --> Router
  Sentiment --> Router
  Bull --> Router
  Bear --> Router
  ResearchMgr --> Router
  PM --> Router
  RiskAgent --> Router
  ComplianceAgent --> Router
  Chair --> Router
  Trader --> Router
  Router --> Qwen
  Router --> Mock

  Macro -- "tool calls" --> Gateway
  Technical -- "tool calls" --> Gateway
  Sentiment -- "tool calls" --> Gateway
  ResearchMgr -- "tool calls" --> Gateway
  PM -- "tool calls" --> Gateway
  RiskAgent -- "tool calls" --> Gateway
  ComplianceAgent -- "tool calls" --> Gateway
  Trader -- "tool calls" --> Gateway
  Gateway --> MCP
  Gateway --> MarketSkill
  Gateway --> OrderBookSkill
  Gateway --> PortfolioSkill
  Gateway --> RiskSkill
  Gateway --> ComplianceSkill
  Gateway --> BrokerSkill
  Gateway --> BenchmarkSkill

  PM -- "TradeProposal basket" --> RiskSvc
  RiskSvc --> ComplianceSvc
  ComplianceSvc --> CommitteeSvc
  CommitteeSvc --> BrokerSvc
  BrokerSvc --> IOC
  IOC --> Exchange
  Exchange --> Sweep
  Sweep --> Fill
  Fill --> Ledger
  Ledger --> LongShort
  LongShort --> PortfolioState
  PortfolioState --> PortfolioPanel
  Exchange --> OrderBookPanel
  MarketBundle --> Candles
  EventClock --> ReleasedEvents
  Slate --> CandidatePanel
  Bench --> BenchmarkPanel
  Recorder --> DecisionFlow
  Recorder --> AgentLive
  Recorder --> Workbench
  Recorder --> RuntimePanel
```

The agents do not mutate financial state directly. They propose, debate, and explain actions; deterministic services own risk checks, compliance checks, broker routing, order-book matching, long/short accounting, replay persistence, and benchmark proof.

Alibaba Cloud evidence in this repository is the deployment path and proof checklist: `infra/alibaba/`, `docker-compose.yml`, and `docs/ALIBABA_CLOUD_PROOF.md`. Irrefutable deployment proof still needs runtime artifacts from Alibaba ECS, such as a proof video, screenshots, `docker compose ps`, `/health`, and `/api/proof/qwen` output from the deployed host.

## Repository Layout

```text
apps/api/                         FastAPI backend, agents, simulation, recordings
apps/api/app/agents/qwen_client.py Qwen Cloud structured-output client
apps/api/app/skills/              Permissioned tool gateway and MCP adapters
apps/api/app/services/            Exchange, ledger, risk, compliance, recordings
apps/api/app/recording_fixtures/  Bundled replay fixture seeded on startup
apps/web/                         React/Vite dashboard
configs/                          Local MCP and risk-limit defaults
docs/                             Architecture, proof, deployment, demo, benchmarking
```

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Dashboard: http://localhost:5173
- API health: http://localhost:8000/health
- Qwen ping: http://localhost:8000/api/proof/qwen
- MCP status: http://localhost:8000/api/mcp/status

On startup, the API seeds the bundled replay fixture into `SIMULATION_RECORDINGS_DIR` if it is missing. Runtime-created recordings remain ignored by git.

## Qwen Cloud Setup

Set your Qwen Cloud DashScope key in `.env`:

```bash
DASHSCOPE_API_KEY=your_dashscope_key_here
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_REASONING=qwen3.7-plus
QWEN_MODEL_FAST=qwen3.7-flash
QWEN_MODEL_CODER=qwen3-coder-plus
QWEN_JSON_MODE=true
QWEN_STRUCTURED_OUTPUT_STRATEGY=json_object
QWEN_ENABLE_THINKING=false
MAX_QWEN_CALLS_PER_CYCLE=12
MAX_QWEN_TOOL_CALLS_PER_AGENT=6
MAX_PARALLEL_AGENT_CALLS=5
```

Provider resolution is intentionally simple for submission clarity:

1. If `DASHSCOPE_API_KEY` is present, the backend uses Qwen Cloud.
2. If no Qwen key is present, the backend uses deterministic mock agents for offline tests and demo resilience.

Refer to `https://github.com/Xuanming-Guo/Agentic-hedge-fund/blob/main/docs/ALIBABA_CLOUD_PROOF.md` for proof of Qwen Cloud Use

## Bundled Replay

The curated replay is:

```text
Example Full Day Simulation 11th June 2025
```

Fixture location:

```text
apps/api/app/recording_fixtures/example-full-day-simulation-2025-06-11/
```

The large frame file is committed as compressed chunks:

```text
frames.ndjson.gz.part001
frames.ndjson.gz.part002
```

At API startup, `app.scripts.seed` reconstructs the runtime `frames.ndjson` sidecar inside `SIMULATION_RECORDINGS_DIR`. This keeps the GitHub repository focused on one curated replay while leaving user-generated recordings ignored:

```text
recordings/
apps/api/recordings/
```

To demo it:

1. Start the app with Docker.
2. Open the dashboard.
3. Open **Simulations**.
4. Select **Example Full Day Simulation 11th June 2025**.
5. Replay using action/keyframes for fast loading.
6. Run the benchmark panel to show `multi_agent` vs `single_agent`, or use the benchmark already saved in the final replay snapshot.

## Agent Society Flow

1. **CoordinatorAgent** assigns the portfolio slate and tasks.
2. **MacroAnalystAgent**, **TechnicalAnalystAgent**, and **SentimentNewsAnalystAgent** review point-in-time context.
3. **BullResearcherAgent** and **BearResearcherAgent** debate catalyst quality and downside risk.
4. **ResearchManagerAgent** computes consensus, disagreement, and candidate ranking.
5. **PortfolioManagerAgent** proposes up to three evidence-led trades: primary, hedge, or relative value.
6. **RiskManagerAgent** resizes or rejects proposals using exposure, volatility, depth, and per-name limits.
7. **ComplianceOfficerAgent** blocks future-data leakage, irrelevant evidence, and restricted conditions.
8. **InvestmentCommitteeChairAgent** resolves disagreements and approves, resizes, defers, or rejects.
9. **ExecutionTraderAgent** routes simulated marketable IOC child orders into the deterministic exchange.
10. **PortfolioLedger** updates cash, positions, realized PnL, unrealized PnL, and exposure.

## Benchmark

The Benchmark panel for comparison:

```text
multi_agent vs single_agent
```

It reports:

- Total return
- Max drawdown
- Risk violations
- Directional accuracy
- Decision quality
- ASAI, the Agent Society Advantage Index

```text
POST /api/recordings/{recording_id}/benchmark
```

Live simulations can be benchmarked directly:

```text
POST /api/simulations/{simulation_id}/benchmark
```

The benchmark compares the saved multi-agent outcome against a single-agent baseline and other deterministic baselines.

## Summary

- Track: **Agent Society**.
- Public repository URL.
- Open-source license visible: `LICENSE`.
- Architecture diagram: this README and `docs/ARCHITECTURE.md`.
- Main public demo video: 
- Separate Alibaba Cloud deployment proof recording.
- Alibaba proof instructions: `docs/ALIBABA_CLOUD_PROOF.md`.
- Qwen proof endpoint: `/api/proof/qwen`.
- Benchmark proof: dashboard Benchmark panel showing `multi_agent` and `single_agent`.
- Text description of features and functionality.

## Local Development

```bash
make setup
make dev
make seed
make test
make lint
make benchmark
make mcp-smoke
```

Useful direct checks:

```bash
cd apps/api
python -m pytest
python -m ruff check app
python -m mypy app

cd apps/web
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

## Actual Market Data

The launcher can import historical bars for manually entered stock tickers, then generate a deterministic replayable limit-order book from those bars. yfinance is the default no-key provider; Alpaca remains optional:

```bash
MARKET_DATA_MODE=synthetic
REAL_MARKET_TICKERS=AAPL,NVDA,MSFT,TSLA,AMD,AMZN,META,GOOGL,JPM,XOM
YFINANCE_INTERVAL=1m
YFINANCE_LOOKBACK_PERIOD=5d
ALPACA_API_KEY_ID=
ALPACA_API_SECRET_KEY=
ALPACA_DATA_FEED=iex
```

Older dates may use daily OHLCV as an anchor for deterministic intraday-shaped replay when 1-minute bars are unavailable. Order-book depth is simulated for replay consistency; it is not a live consolidated Level 2 feed.

## Safety

- Simulated trades only.
- No real brokerage execution.
- No investment advice.
- Replays are redacted before being saved or served publicly.
- Future-data leakage checks prevent agents from seeing unreleased events.

## License

MIT. See `LICENSE`.
