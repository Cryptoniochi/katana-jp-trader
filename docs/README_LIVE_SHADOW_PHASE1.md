# Live Trading Preparation Phase 1

Phase 1 adds a safe execution-mode boundary and a persistent Shadow Broker.
It does not contain a kabu Station order-submission implementation and is not
connected to the resident Paper Trading process.

## Modes

- `paper`: default mode when no environment variable is configured.
- `shadow`: records the order plan to JSON Lines without sending a request.
- `live`: always rejected in Phase 1, even when both arming values are valid.

`ExecutionModeSettings.from_environment()` reads these variables:

```text
KATANA_EXECUTION_MODE=paper|shadow|live
KATANA_LIVE_TRADING_ARMED=YES
KATANA_LIVE_TRADING_CONFIRMATION=KATANA-LIVE-YYYY-MM-DD
```

The last two values form a daily double unlock. They are validated now so the
contract is testable before a real broker implementation is introduced.

## Shadow ledger

`ShadowBroker` implements the existing `BrokerAdapter` protocol. Its default
ledger is:

```text
reports/live/shadow_orders.jsonl
```

Submitting an order:

1. creates a deterministic SHA-256 idempotency key;
2. appends and fsyncs one `submitted` event;
3. returns `OrderStatus.QUEUED` with zero filled quantity;
4. does not create a position or change cash;
5. performs no network operation.

Re-submitting the identical order returns the existing record without adding a
line. Reusing an order ID with different content raises
`ShadowOrderConflictError`. The ledger is reloaded on restart, preserving the
same idempotency behavior.

## Phase 1 safety boundary

- Existing runtime commands do not import or instantiate these components.
- No service, scheduler, dashboard, or task configuration is changed.
- `ExecutionModeRouter` cannot return a Live Broker.
- Live mode raises `LiveTradingUnavailableError` after the double unlock is
  validated.

Integration with the Paper signal path belongs to Phase 2 and must only occur
after the full test suite passes.
