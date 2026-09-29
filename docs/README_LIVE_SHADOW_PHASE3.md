# Live Shadow Phase 3

Phase 3 connects the isolated Paper-to-Shadow replicator to the resident
Paper Trading composition and adds an atomic daily reconciliation report.

## Safety contract

- Shadow replication is disabled by default.
- The existing scheduled task command is unchanged.
- No live brokerage request is implemented or enabled.
- Only Paper orders that reached the Paper Broker path are eligible.
- Risk-blocked and failed Paper orders are not recorded as Shadow orders.
- Shadow ledger and report failures are isolated from Paper Trading.
- The Shadow ledger remains plan-only: it creates no fills, positions, or
  cash movements.

## Explicit activation

After validation, the Paper Trading process can opt in with:

```text
--enable-shadow-replication
```

Optional destinations:

```text
--shadow-ledger-path reports/live/shadow_orders.jsonl
--shadow-reconciliation-report-path reports/live/shadow_reconciliation.json
```

The paths can also be supplied with
`KATANA_SHADOW_LEDGER_PATH` and
`KATANA_SHADOW_RECONCILIATION_REPORT_PATH`. The environment does not enable
replication by itself; the CLI enable flag is still required.

## Reconciliation output

`reports/live/shadow_reconciliation.json` is written atomically and contains:

- the Tokyo trading date;
- consistency state;
- recorded, existing, skipped, failed, and mismatch counts;
- one idempotent record per Paper order ID;
- the Shadow broker order ID and idempotency key.

The report starts in `waiting`, becomes `consistent` when all observed orders
match, and becomes `attention` if a failure or mismatch is recorded.

## Phase boundary

Phase 3 does not enable live order submission. Live mode remains locked by the
daily double-unlock contract from Phase 1 and still raises
`LiveTradingUnavailableError` after a successful unlock check.
