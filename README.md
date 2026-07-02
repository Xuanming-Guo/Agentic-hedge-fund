# Agentic Hedge Fund

**A Qwen Cloud Agent Society that runs a simulated hedge-fund trading desk.**

Agentic Hedge Fund is a replay market simulation where specialized Qwen agents decompose a trading day, debate catalysts, route a basket through portfolio/risk/compliance/committee gates, execute simulated fills, and benchmark the agent society against a required `single_agent` baseline.

This is a simulation and education project only. It does not connect to a real brokerage, does not execute real trades, and does not provide investment advice.

## Hackathon Track

Qwen Cloud Global AI Hackathon - **Track 3: Agent Society**.

## Inspiration

I recently became a quant dev, which pushed me deeper into market microstructure, portfolio construction, execution logic, and the reality that trading decisions are rarely one-dimensional. At the same time, I have been getting more interested in AI agents and how far they can go beyond normal chat-style reasoning.

One thing that bothered me is that normal AI does not really trade properly. A single model can sound confident, but it usually does not behave like a real desk: it does not separate research from risk, it does not debate opposing views, it does not enforce compliance, it does not reason about order-book liquidity, and it often jumps straight from "bullish" to "buy" without the controls that a real trading system would need.

So I built Agentic Hedge Fund as an experiment: can a Qwen-powered agent society make better, safer, and more explainable simulated trading decisions than a normal single-agent AI trading setup? The project compares specialized agents against a `single_agent` baseline on the same replay so the extra complexity has to justify itself with measurable results.

## What The Demo Shows

- A dockable trading dashboard with market replay candles, order book, portfolio, and optional agent/governance panels.
- An already simulated full-day replay named **`Example Full Day Simulation 11th June 2025`** so reviewers can open a realistic saved run immediately after cloning.
- Qwen agents evaluating up to 10 tickers as a portfolio slate.
- Evidence-led allocation roles: primary catalyst, hedge candidate, relative-value candidate, and watchlist/hold reasons.
- Simulated long/short marketable IOC fills through a deterministic order book and ledger.
- Agent chat details with formatted structured JSON, tool calls, validation notes, and state transitions.
- Replay keyframes for fast loading of full-day recordings.
- Agent Society benchmark proof: `multi_agent` vs `single_agent`.

### Requirements

Before running the project, install:

- **Git** for cloning the repository.
- **Docker Desktop** or Docker Engine.
- **Docker Compose v2**, available as `docker compose`.
- A **Qwen Cloud DashScope API key** for live Qwen agent runs.


## Architecture

[Open full-size architecture diagram](docs/assets/architecture/full-system-architecture.svg)

[![Full-system architecture diagram](docs/assets/architecture/full-system-architecture.svg)](docs/assets/architecture/full-system-architecture.svg)

```mermaid
flowchart TB
  User["Reviewer browser"] --> Web["React dockable trading cockpit"]
  Web --> Panels["Candles, order book, portfolio, agent live, workbench, committee, benchmark"]
  Web -- "REST controls" --> API["FastAPI API"]
  Web -- "WebSocket snapshots" --> API
  API --> Engine["Simulation Engine"]
  API --> Replay["Recording + replay keyframes"]
  API --> Proof["Qwen, MCP, skills, Alibaba proof endpoints"]
  Engine --> Society["Qwen Agent Society"]
  Society --> Agents["Coordinator, analysts, bull/bear, PM, risk, compliance, committee, trader, narrator"]
  Society --> Tools["Qwen Tool Gateway + MCP skills"]
  Tools --> Governance["Risk + compliance + broker + committee"]
  Governance --> Execution["Marketable IOC order -> order book sweep -> fill/partial/unfilled"]
  Execution --> Ledger["PortfolioLedger long/short accounting"]
  Ledger --> Portfolio["cash, equity, positions, realized/unrealized PnL, exposure"]
  Engine --> Benchmark["multi_agent vs single_agent ASAI benchmark"]
  Engine --> Replay
  Replay --> Web
  Portfolio --> Web
  Benchmark --> Web
  Proof --> Runtime["Alibaba ECS / Docker Compose / Qwen Cloud proof surface"]
```

The agents do not mutate financial state directly. They propose, debate, and explain actions; deterministic services own risk checks, compliance checks, broker routing, order-book matching, long/short accounting, replay persistence, and benchmark proof.

## Video/Demo Link
https://youtu.be/nzWGWwEkI68

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
git clone https://github.com/Xuanming-Guo/Agentic-hedge-fund.git
cd .\Agentic-hedge-fund\
cp .env.example .env
# Put your API key in DASHSCOPE_API_KEY
docker compose up --build
```

Open:

- Dashboard: http://localhost:5173
- API health: http://localhost:8000/health
- Qwen ping: http://localhost:8000/api/proof/qwen
- MCP status: http://localhost:8000/api/mcp/status

On startup, the API waits for Postgres, runs Alembic migrations, seeds scenarios, and seeds the bundled replay fixture into `SIMULATION_RECORDINGS_DIR` if it is missing. Runtime-created recordings remain ignored by git.

If the dashboard opens but the scenario list or saved simulations are empty, the API probably did not finish startup and the seed step did not run. Check:

```bash
curl http://localhost:8000/health
docker compose logs api postgres
```

The API logs should show `Database is reachable`, Alembic migrations running, scenario seeding, and either the bundled replay being seeded or already present. Seeing a few `Waiting for database` lines is normal during startup; it is only a problem if it never reaches `Database is reachable`.

If Docker networking was stale, restart the stack:

```bash
docker compose down --remove-orphans
docker compose up --build
```

If you are testing two cloned copies on the same machine, give the clean clone a separate Compose project name so networks, containers, and volumes do not collide:

```bash
docker compose -p ahf-clean up --build
```

As a last resort after stopping this project and any other Compose projects you care about, prune unused Docker networks:

```bash
docker network prune
```

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

Alibaba Cloud evidence in this repository is the deployment path and proof checklist: `infra/alibaba/`, `docker-compose.yml`, and `docs/ALIBABA_CLOUD_PROOF.md`.

Refer to https://github.com/Xuanming-Guo/Agentic-hedge-fund/blob/main/docs/ALIBABA_CLOUD_PROOF.md for proof of Qwen Cloud Use in code

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

The Benchmark panel makes the Agent Society comparison explicit:

```text
multi_agent vs single_agent
```

For the included full-day replay benchmark, the multi-agent society was scored across **516 replay keyframes** against a single-agent baseline.

Latest replay benchmark result:

- **ASAI score:** 25.11
- **Return delta:** +0.24 pts
- **Risk avoided:** 2 fewer risk violations

| Metric | multi_agent | single_agent |
|---|---:|---:|
| Return | 0.23% | -0.00% |
| Max drawdown | 0.65% | 1.35% |
| Risk violations | 0 | 2 |
| Directional accuracy | 78% | 67% |
| Decision quality | 100% | 82% |

The result I cared about was not only return. The agent society also showed lower drawdown, fewer risk violations, higher directional accuracy, and better decision quality on the replay benchmark.

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
