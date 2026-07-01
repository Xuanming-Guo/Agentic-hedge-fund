# Architecture

Agentic Hedge Fund is a replay-first Qwen Agent Society and simulated hedge-fund trading desk. The system links a dockable dashboard, FastAPI control plane, Qwen structured-output agents, permissioned tools, MCP servers, deterministic risk/compliance/broker/exchange services, saved full-day replays, and an explicit `multi_agent` vs `single_agent` benchmark.

## Zoomable Whole System Map

[Open full-size architecture diagram](assets/architecture/full-system-architecture.svg)

[![Full-system architecture diagram](assets/architecture/full-system-architecture.svg)](assets/architecture/full-system-architecture.svg)

GitHub squeezes very large inline Mermaid diagrams into the Markdown column. The SVG above is the readable zoomable version, and the editable Mermaid source lives at `docs/assets/architecture/full-system-architecture.mmd`.

## Agent Society Decision Cycle

```mermaid
flowchart LR
  Clock["Market clock + released events"] --> Slate["Candidate slate: up to 10 active tickers"]
  Slate --> Coordinator["CoordinatorAgent assigns slate tasks"]
  Coordinator --> Macro["MacroAnalystAgent"]
  Coordinator --> Technical["TechnicalAnalystAgent"]
  Coordinator --> Sentiment["SentimentNewsAnalystAgent"]
  Coordinator --> Bull["BullResearcherAgent"]
  Coordinator --> Bear["BearResearcherAgent"]

  Macro --> Consensus["ResearchManagerAgent: consensus, disagreement, ranks"]
  Technical --> Consensus
  Sentiment --> Consensus
  Bull --> Debate["Bull/Bear debate evidence"]
  Bear --> Debate
  Debate --> Consensus

  Consensus --> PM["PortfolioManagerAgent: primary, hedge, relative_value, watchlist"]
  PM --> Proposal["PortfolioAllocationProposal: max 3 routed trades"]
  Proposal --> Risk["RiskManagerAgent"]
  Risk --> Compliance["ComplianceOfficerAgent"]
  Compliance --> Chair["InvestmentCommitteeChairAgent"]
  Chair --> Trader["ExecutionTraderAgent"]
  Trader --> DecisionTrace["AgentDecisionTrace + AgentActivityDetail"]
```

Each agent returns validated structured JSON. The society can disagree, resize, defer, reject, or route simulated orders, but state changes only happen after deterministic service checks.

## Trade Execution, Fills, And Long/Short Accounting

```mermaid
flowchart TB
  Proposal["TradeProposal: symbol, side, quantity, evidence_ids"] --> Risk["RiskService"]
  Risk -->|approve or resize| Compliance["ComplianceService"]
  Risk -->|reject| RiskStop["No trade: risk rejection recorded"]
  Compliance -->|valid direct evidence and no leakage| Committee["InvestmentCommitteeService"]
  Compliance -->|invalid evidence or leakage| ComplianceStop["No trade: compliance rejection recorded"]
  Committee -->|approve / approve_resized| Broker["BrokerService"]
  Committee -->|defer / no_trade| CommitteeStop["No trade: committee decision recorded"]
  Broker -->|accepted| IOC["Marketable IOC limit order"]
  Broker -->|rejected| BrokerStop["No route: broker rejection recorded"]

  IOC --> Book["LimitOrderBook"]
  Book --> BuyPath["BUY: sweep visible asks"]
  Book --> SellPath["SELL: sweep visible bids"]
  BuyPath --> Fill["filled / partial / unfilled"]
  SellPath --> Fill
  Fill --> Ledger["PortfolioLedger.apply_fill"]

  Ledger --> BuyLogic["Buy: open/increase long OR cover/reduce short"]
  Ledger --> SellLogic["Sell: reduce/close long OR open/increase short"]
  BuyLogic --> Portfolio["PortfolioState"]
  SellLogic --> Portfolio
  Portfolio --> Metrics["cash, equity, realized PnL, unrealized PnL, gross exposure, net exposure"]
  Portfolio --> UI["Portfolio panel + recent fills + PnL graph"]
```

Approved orders are not real trades. They are simulated IOC child orders matched against deterministic visible liquidity so the replay can show fills, partial fills, or unfilled outcomes.

## Replay, Recording, And Keyframe Loading

```mermaid
flowchart LR
  Live["Live simulation snapshots"] --> Recorder["RecordingService"]
  Recorder --> Manifest["manifest.json"]
  Recorder --> Frames["frames.ndjson runtime sidecar"]
  Recorder --> Activity["activity_details.json"]
  Recorder --> Skills["skill_call_details.json"]
  Fixture["Bundled fixture chunks: frames.ndjson.gz.part001/part002"] --> Seed["app.scripts.seed"]
  Seed --> Frames

  Manifest --> ListAPI["GET /api/recordings"]
  Frames --> Keyframes["GET /api/recordings/{id}/keyframes"]
  Frames --> FullFrames["GET /api/recordings/{id}/frames"]
  Activity --> DetailAPI["GET /api/recordings/{id}/agent-activity/{activity_id}"]

  ListAPI --> Modal["Simulations modal"]
  Keyframes --> FastReplay["Action replay loads first"]
  FullFrames --> LazyReplay["All frames load lazily"]
  DetailAPI --> Chat["Agent Society Live chat detail"]
```

The bundled replay `Example Full Day Simulation 11th June 2025` is seeded into the Docker recording volume on startup if it is missing.

## Dashboard Dockable Workspace Data Flow

```mermaid
flowchart TB
  Snapshot["SimulationSnapshot via WebSocket or replay frame"] --> Workspace["DockableWorkspace"]
  Workspace --> Market["Market category"]
  Workspace --> Agents["Agents category"]
  Workspace --> Governance["Governance category"]
  Workspace --> Diagnostics["Diagnostics category"]

  Market --> Candles["Market Replay Candles"]
  Market --> OrderBook["Order Book"]
  Market --> Portfolio["Portfolio"]
  Market --> Events["Released Events"]

  Agents --> Live["Agent Society Live"]
  Agents --> Workbench["Agent Workbench"]
  Agents --> Slate["Candidate Slate"]

  Governance --> Committee["Investment Committee"]
  Governance --> Benchmark["Agent Society Benchmark"]

  Diagnostics --> Runtime["Agent Runtime"]
  Diagnostics --> Flow["Agent Decision Flow"]

  Snapshot --> Candles
  Snapshot --> OrderBook
  Snapshot --> Portfolio
  Snapshot --> Events
  Snapshot --> Live
  Snapshot --> Workbench
  Snapshot --> Slate
  Snapshot --> Committee
  Snapshot --> Benchmark
  Snapshot --> Runtime
  Snapshot --> Flow
```

Only the core cockpit panels are visible by default; secondary panels can be added, removed, and repositioned without changing backend state.

## Benchmark And Agent Society Proof

```mermaid
flowchart LR
  Snapshot["Live snapshot or replay keyframe"] --> Bench["Benchmark engine"]
  Bench --> Multi["multi_agent metrics"]
  Bench --> Single["single_agent baseline"]
  Bench --> Rules["rule_based baseline"]
  Bench --> Hold["buy_and_hold baseline"]
  Bench --> Random["random baseline"]
  Multi --> ASAI["Agent Society Advantage Index"]
  Single --> ASAI
  Rules --> ASAI
  Hold --> ASAI
  Random --> ASAI
  ASAI --> Card["Benchmark card: side-by-side multi_agent vs single_agent"]
  Card --> Submission["Track 3 Agent Society proof"]
```

Replay benchmarking scores keyframes only, so a full-day replay can show the required society-vs-single-agent comparison without loading every raw frame.

## Alibaba Cloud Proof Surface

Code and documentation evidence for deployment readiness lives in:

- `infra/alibaba/`
- `docker-compose.yml`
- `docs/ALIBABA_CLOUD_PROOF.md`
- `/health`
- `/api/proof/qwen`
- `/api/mcp/status`

Those files prove the deployment path and the proof checklist. Irrefutable deployment proof still requires runtime artifacts from Alibaba ECS, such as an ECS console recording, `docker compose ps`, deployed `/health`, deployed `/api/proof/qwen`, and dashboard screenshots or video from the deployed host.

## Service Boundaries

- Agents produce structured recommendations, debate records, and rationale.
- Risk, compliance, broker, exchange, and ledger services enforce state transitions.
- Qwen and tool outputs are validated before they can influence simulated orders.
- The frontend receives redacted API and WebSocket payloads, never secret keys.

## Determinism

Mock mode is deterministic for tests and offline demos. Synthetic depth and replay order books are generated from scenario/bars so saved recordings can be replayed consistently. Agents only receive point-in-time bars/events and never future unreleased events.
