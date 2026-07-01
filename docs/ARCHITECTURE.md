# Architecture

Agentic Hedge Fund is a replay-first Qwen Agent Society and simulated hedge-fund trading desk. The system links a dockable dashboard, FastAPI control plane, Qwen structured-output agents, permissioned tools, MCP servers, deterministic risk/compliance/broker/exchange services, saved full-day replays, and an explicit `multi_agent` vs `single_agent` benchmark.

## Whole System Map

```mermaid
flowchart TB
  User["Reviewer / operator"]

  subgraph Runtime["Alibaba Cloud / Docker Runtime"]
    ECS["Alibaba ECS host or local Docker host"]
    Compose["docker compose"]
    WebContainer["web container: React/Vite"]
    APIContainer["api container: FastAPI"]
    DB[("PostgreSQL")]
    RecVol[("simulation-recordings volume")]
    Env["DASHSCOPE_API_KEY server-side only"]
    Proof["Deployment proof surface: infra/alibaba, docker-compose.yml, docs/ALIBABA_CLOUD_PROOF.md"]
  end

  subgraph Cockpit["Frontend Trading Cockpit"]
    Shell["Dashboard shell + dockable workspace"]
    TopBar["Connection, replay, save, speed, spinner/progress"]
    Simulations["Simulations modal"]
    Candles["Market Replay Candles"]
    BookPanel["Order Book"]
    Portfolio["Portfolio: positions, PnL, exposure, recent fills"]
    Live["Agent Society Live"]
    Workbench["Agent Workbench: states, decisions, debate"]
    SlatePanel["Candidate Slate"]
    EventsPanel["Released Events"]
    RuntimePanel["Agent Runtime"]
    CommitteePanel["Investment Committee"]
    BenchmarkPanel["Agent Society Benchmark"]
    FlowPanel["Agent Decision Flow"]
  end

  subgraph PublicAPI["FastAPI Public API"]
    Controls["/api/simulations controls"]
    Recordings["/api/recordings list, keyframes, frames, resume"]
    Activity["/api/*/agent-activity"]
    Committees["/api/*/committee-decisions and consensus"]
    BenchAPI["/api/*/benchmark"]
    QwenProof["/api/proof/qwen"]
    MCPStatus["/api/mcp/status"]
    SkillsAPI["/api/skills and /api/skills/calls"]
    Socket["/api/ws/simulations/{id}"]
  end

  subgraph Core["Simulation Core"]
    Engine["SimulationEngine"]
    Scenario["Scenario + market clock"]
    MarketData["MarketDataMetadata: synthetic, yfinance, Alpaca optional"]
    Bars["Market replay bars"]
    Events["Point-in-time released events"]
    Orderbooks["Per-symbol deterministic order books"]
    CandidateSlate["Multi-ticker candidate slate"]
    PortfolioHistory["Portfolio history time series"]
    Recorder["RecordingService: manifest, frames, keyframes, sidecars"]
    Fixture["Bundled replay fixture: Example Full Day Simulation 11th June 2025"]
    Benchmark["Benchmark engine: ASAI, multi_agent, single_agent"]
  end

  subgraph Agents["Qwen Agent Society"]
    Router["Qwen model router"]
    Qwen["Qwen Cloud structured JSON API"]
    Mock["Deterministic mock fallback"]
    Coordinator["CoordinatorAgent"]
    Macro["MacroAnalystAgent"]
    Technical["TechnicalAnalystAgent"]
    Sentiment["SentimentNewsAnalystAgent"]
    Bull["BullResearcherAgent"]
    Bear["BearResearcherAgent"]
    ResearchManager["ResearchManagerAgent"]
    PortfolioManager["PortfolioManagerAgent"]
    RiskManager["RiskManagerAgent"]
    ComplianceOfficer["ComplianceOfficerAgent"]
    Chair["InvestmentCommitteeChairAgent"]
    ExecutionTrader["ExecutionTraderAgent"]
    Narrator["DemoNarratorAgent"]
  end

  subgraph Gateway["Tool Gateway + MCP"]
    ToolGateway["Qwen Tool Gateway"]
    MCP["Local MCP servers"]
    MarketSkill["market_get_context"]
    EventSkill["released_events"]
    BookSkill["orderbook_get_depth"]
    PortfolioSkill["portfolio_get_state"]
    RiskSkill["risk_check_order"]
    ComplianceSkill["compliance_check_evidence"]
    BrokerSkill["broker_route_approved_order"]
    BenchmarkSkill["benchmark_run"]
  end

  subgraph Execution["Governance + Execution"]
    Proposal["PortfolioAllocationProposal: up to 3 trades"]
    Risk["RiskService: resize, approve, reject"]
    Compliance["ComplianceService: symbol evidence + future-data firewall"]
    Committee["InvestmentCommitteeService: approve, approve_resized, defer, no_trade"]
    Broker["BrokerService: accept/reject route"]
    IOC["Marketable IOC limit child order"]
    Exchange["LimitOrderBook exchange"]
    Sweep["Buy sweeps visible asks; sell sweeps visible bids"]
    Fill["filled / partially_filled / unfilled"]
    Ledger["PortfolioLedger"]
    LongShort["Long/short accounting"]
    State["PortfolioState: cash, equity, realized/unrealized PnL, exposure"]
  end

  User --> WebContainer
  ECS --> Compose
  Compose --> WebContainer
  Compose --> APIContainer
  Compose --> DB
  Compose --> RecVol
  Env --> APIContainer
  Proof --> ECS

  WebContainer --> Shell
  Shell --> TopBar
  Shell --> Simulations
  Shell --> Candles
  Shell --> BookPanel
  Shell --> Portfolio
  Shell --> Live
  Shell --> Workbench
  Shell --> SlatePanel
  Shell --> EventsPanel
  Shell --> RuntimePanel
  Shell --> CommitteePanel
  Shell --> BenchmarkPanel
  Shell --> FlowPanel

  TopBar -- "REST controls" --> Controls
  Simulations -- "saved replay open" --> Recordings
  Shell -- "WebSocket snapshots" --> Socket
  BenchmarkPanel -- "live/replay benchmark" --> BenchAPI
  Live -- "activity detail" --> Activity
  Workbench -- "activity detail" --> Activity
  CommitteePanel --> Committees
  RuntimePanel --> QwenProof
  Workbench --> SkillsAPI
  RuntimePanel --> MCPStatus

  Controls --> Engine
  Socket --> Engine
  Recordings --> Recorder
  BenchAPI --> Benchmark
  QwenProof --> Qwen
  MCPStatus --> MCP
  SkillsAPI --> ToolGateway

  Engine --> Scenario
  Engine --> MarketData
  Engine --> Bars
  Engine --> Events
  Engine --> Orderbooks
  Engine --> CandidateSlate
  Engine --> PortfolioHistory
  Engine --> Recorder
  Fixture --> Recorder
  Recorder --> RecVol
  Engine --> DB

  Engine --> Coordinator
  Coordinator --> CandidateSlate
  CandidateSlate --> Macro
  CandidateSlate --> Technical
  CandidateSlate --> Sentiment
  Macro --> ResearchManager
  Technical --> ResearchManager
  Sentiment --> ResearchManager
  Bull --> ResearchManager
  Bear --> ResearchManager
  ResearchManager --> PortfolioManager
  PortfolioManager --> RiskManager
  RiskManager --> ComplianceOfficer
  ComplianceOfficer --> Chair
  Chair --> ExecutionTrader
  Narrator --> BenchmarkPanel

  Coordinator --> Router
  Macro --> Router
  Technical --> Router
  Sentiment --> Router
  Bull --> Router
  Bear --> Router
  ResearchManager --> Router
  PortfolioManager --> Router
  RiskManager --> Router
  ComplianceOfficer --> Router
  Chair --> Router
  ExecutionTrader --> Router
  Narrator --> Router
  Router --> Qwen
  Router --> Mock

  Macro --> ToolGateway
  Technical --> ToolGateway
  Sentiment --> ToolGateway
  Bull --> ToolGateway
  Bear --> ToolGateway
  ResearchManager --> ToolGateway
  PortfolioManager --> ToolGateway
  RiskManager --> ToolGateway
  ComplianceOfficer --> ToolGateway
  ExecutionTrader --> ToolGateway
  ToolGateway --> MCP
  ToolGateway --> MarketSkill
  ToolGateway --> EventSkill
  ToolGateway --> BookSkill
  ToolGateway --> PortfolioSkill
  ToolGateway --> RiskSkill
  ToolGateway --> ComplianceSkill
  ToolGateway --> BrokerSkill
  ToolGateway --> BenchmarkSkill

  PortfolioManager -- "proposal basket" --> Proposal
  Proposal --> Risk
  Risk --> Compliance
  Compliance --> Committee
  Committee --> Broker
  Broker --> IOC
  IOC --> Exchange
  Exchange --> Sweep
  Sweep --> Fill
  Fill --> Ledger
  Ledger --> LongShort
  LongShort --> State
  State --> Portfolio
  State --> PortfolioHistory
  Orderbooks --> BookPanel
  Bars --> Candles
  Events --> EventsPanel
  CandidateSlate --> SlatePanel
  Recorder --> Live
  Recorder --> Workbench
  Recorder --> FlowPanel
  Benchmark --> BenchmarkPanel
```

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
