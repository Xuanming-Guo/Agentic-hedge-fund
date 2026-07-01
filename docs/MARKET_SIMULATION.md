# Market Simulation

The default trading day runs from 09:25 pre-market initialization through 16:00 close. The tick interval is one simulated minute.

Tick order:

1. Advance the clock.
2. Release point-in-time events.
3. Update visible bars.
4. Seed background orderbook liquidity.
5. Run agent decision cycles on cadence or major events.
6. Broker validates orders.
7. Exchange matches by price-time priority.
8. Ledger settles fills.
9. Risk and compliance state updates.
10. WebSocket broadcasts the snapshot.

Order types supported by the pure orderbook core include market, limit, stop, and stop-limit, with DAY, IOC, and FOK time-in-force.
