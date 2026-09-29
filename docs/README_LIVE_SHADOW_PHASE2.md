# Live Trading Preparation Phase 2

Phase 2 adds an isolated replication service between completed Paper Broker
processing and the persistent Shadow order ledger.

It still does not connect the replication service to the resident scheduler and
does not implement a kabu Station live-order request.

## Replication boundary

`PaperShadowReplicationService` accepts the existing
`BacktestQueueExecutionBatchResult` after the Paper Broker step.

- A Paper item that reached the Broker sync step is copied to Shadow.
- A Paper item rejected by the Risk Gate never appears in the execution batch.
- A failed Paper item is marked `skipped` and is not copied.
- An item without a Broker sync result is marked `skipped`.
- Repeated replication is idempotent and returns `existing`.
- A Shadow write failure is captured as `failed` by default and never changes
  the already-completed Paper result.
- Offline validation can use `continue_on_error=False` to raise immediately.

## Reconciliation

Each replicated order is compared using all `TradeOrder` fields plus the common
Broker snapshot fields:

- client order ID;
- symbol code;
- side;
- quantity;
- zero filled quantity;
- no average fill price.

Any difference produces `mismatch`. Batch totals expose recorded, existing,
skipped, failed, mismatch, and replicated counts.

## Safety boundary

- No resident service constructor is changed.
- No task command or environment variable is changed.
- No Shadow failure can cancel, retry, or alter a Paper order.
- No live-order endpoint or authentication value exists in this phase.

Phase 3 will connect this service behind an explicit Shadow feature flag and add
a daily reconciliation report. That connection must remain disabled by default.
