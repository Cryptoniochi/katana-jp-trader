# Live Phase 5-B: Three-Source Reconciliation Baseline

Phase 5-B compares three independent sources without submitting, cancelling,
or modifying any broker order:

1. Paper executions stored in `trade_executions`, aggregated by `order_id`.
2. Shadow `submitted` events stored in `reports/live/shadow_orders.jsonl`.
3. The GET-only broker inventory created by Phase 5-A.

Paper and Shadow must match on order ID, signal ID, symbol, side, and total
quantity. In the current locked Paper/Shadow stage, the real broker account
must have no active order and no position. Any broker inventory is reported as
`BLOCKED`; KATANA does not cancel or close it automatically.

The first production comparison found that intraday entries were replicated,
but end-of-day forced liquidation orders were not connected to the Shadow
recorder. Phase 5-B also connects that existing liquidation path to the same
idempotent Shadow recorder. A Shadow failure is counted but never prevents the
Paper position from being closed.

This report is a safety baseline, not proof of real order execution. Live order
submission remains unavailable and `live_order_ready` is always `false`.

After running Phase 5-A, execute:

```powershell
.\.venv\Scripts\python.exe `
    -m app.run_three_way_reconciliation `
    --trading-date 2026-10-02
```

The report is written to:

`reports\live\three_way_reconciliation.json`

Exit codes:

- `0`: Paper and Shadow match, broker inventory is empty.
- `1`: A reconciliation or broker inventory issue blocks progression.
- `2`: An input could not be read or parsed.
