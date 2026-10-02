# Tick Protective Stop (Paper + Shadow)

## Purpose

The strategy stop remains available on completed five-minute bars. This
additional guard consumes the latest kabu Station WebSocket tick and evaluates
the current Paper Broker position once per trading cycle (normally every 30
seconds).

## Safety boundary

- No live brokerage order implementation is added or enabled.
- Protective exits use the existing Paper order queue, mandatory pre-trade
  risk gate, Paper Broker, execution ledger, portfolio update, notification,
  trace, and optional Shadow replication path.
- The WebSocket callback only writes to a lock-protected latest-tick buffer.
  Order and SQLite work stays on the trading-cycle thread.
- The default loss threshold is 1% from the Paper Broker average cost.
- After a successful protective exit, strategy state is marked closed while
  retaining the daily `entered` state. A later five-minute bar therefore does
  not emit a duplicate exit or a same-day re-entry.

## Timing and limitation

This is latest-tick-based protection, not broker-native server-side stop
ordering. A trigger is processed at the next KATANA trading cycle, so the
normal maximum observation delay is approximately 30 seconds plus processing
time. Fast markets and gaps can still produce fills below the calculated stop.
Broker-native reverse-limit order support remains a later live-trading phase.

## Verification

Run the targeted tests first, then the full suite. Confirm the next Paper day
contains `tick-protective-stop-v1` only when a position crosses its threshold,
the execution ledger remains balanced, Full-Day Validation passes, and the
Shadow reconciliation report has no mismatch.
