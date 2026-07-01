# Risk And Compliance

Risk limits are configured in `configs/risk_limits.default.yaml`.

Default checks:

- Per-order notional.
- Gross and net exposure.
- Single-name exposure.
- Elevated volatility resizing.
- Short locate availability.
- Cash and buying power.

Compliance checks:

- Evidence IDs must refer to released events.
- Future data references hard-reject.
- Restricted symbols hard-reject.
- Rumor-based trades require stronger evidence.

Human approval can be required for larger simulated orders, compliance warnings, or margin-call conditions. Human approval cannot override hard risk or compliance rejection.

Agentic Hedge Fund does not provide investment advice and does not execute real trades.
