# Project KATANA

Automated Japanese equity trading platform for market-data collection, strategy execution, risk control, monitoring, reporting, carryover recovery, and fail-closed Live Trading.

## Current Status — 2026-10-30

- Git baseline: `f0c0603` — `Reserve live pre-EOD drain window`
- Current execution mode: **Live Trading**
- Trading capital: **JPY 1,000,000**
- Market universe: approximately **3,700** domestic common stocks
- Realtime watchlist: maximum **50** symbols
- Market data: kabu Station REST / WebSocket and 5-minute bars
- J-Quants is not required by the active runtime
- Live production execution is enabled and armed
- KATANA Service is running as the resident Windows service manager
- Current production focus: reliable autonomous Live operation, carryover recovery, EOD safety, and strategy improvement

Performance and account P/L are intentionally not disclosed in this README.

## Strategies

- Opening Range Breakout v2 (ORB)
- Pullback Breakout
- High Breakout

Current ORB production strategy filter:

```text
breakout-bar volume >= 0.8 x average opening-range bar volume
minimum breakout width >= 0.5%
```

Protective stop-loss: **1%**
Take-profit: **2%**

Strategy parameters are changed only when supported by validation evidence. Backtest, Paper Trading, and Live results are not guarantees of future performance.

## Risk Controls

Current production risk configuration:

- Maximum positions: **20**
- Maximum value per symbol: **JPY 200,000**
- Maximum total exposure: **JPY 700,000**
- Minimum cash: **JPY 200,000**
- Maximum daily loss: **JPY 20,000**
- Protective stop-loss: **1%**

Risk, reconciliation, position ownership, carryover recovery, and EOD controls fail closed.

## Universe and Dynamic Watchlist

```text
~3,700 domestic common stocks
        |
        v
Universe Primary Screening
        |
        v
Maximum 300 candidates
        |
        v
Dynamic Watchlist
        |
        v
Maximum 50 realtime symbols
```

Dynamic Watchlist considers liquidity, relative volume, volatility, gap/VWAP distance, strategy fitness, history maturity, and strategy-learning feedback.

Held Live positions are prioritized when building kabu Station registration codes so current positions remain observable even when the daily watchlist changes. Realtime registration remains capped at 50 symbols.

High Breakout screening can evaluate the daily-market universe independently of the 50-symbol realtime registration limit.

## Autonomous Operation

KATANA runs as a resident Windows Scheduled Task and is designed for unattended daily operation.

```text
08:40  Morning Pre-Flight
08:45  Runtime start
09:00  Morning session
11:30  Lunch break
12:30  Afternoon session
15:15  Stop starting new normal Live cycles / begin drain window
15:20  Authoritative EOD liquidation begins
15:30  EOD deadline / fail closed if the account is not flat
15:35  Scheduler grace / shutdown handling
15:40  Daily Report
```

KATANA Service manages:

- Dashboard
- Dynamic Watchlist Scheduler
- Universe Daily Scheduler
- High Breakout Scheduler
- Morning Pre-Flight Scheduler
- Trading Scheduler
- Daily Report Scheduler
- Recovery and health monitoring

## Live Trading

The complete Live execution path has been implemented and commissioned against the real brokerage account.

A concrete Paper-free production composition connects realtime market data, the strategy engine, authoritative brokerage account state, Live risk controls, durable execution/reconciliation, protective exits, carryover recovery, and EOD liquidation.

Current runtime activation:

```text
KATANA_EXECUTION_MODE=live
KATANA_LIVE_PRODUCTION_ENABLED=YES
KATANA_LIVE_TRADING_ARMED=YES
```

The date-specific Live confirmation is operational state and must not be committed to the repository.

Historical Live locks remain sealed:

```text
LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = False
LIVE_BROKER_TRANSPORT_ENABLED = False
LIVE_ORDER_TRANSMISSION_ENABLED = False
```

Concrete Live production uses its separate activation and authorization path rather than modifying those historical locks.

Implemented Live safeguards include:

- Authoritative brokerage cash, order, and position reads
- Durable order and reconciliation state
- No automatic retry after ambiguous order transmission
- Durable daily entry limits
- Protective-stop persistence and restart recovery
- Strategy exits routed through the protected Live sell path
- EOD liquidation with position-ownership verification
- Prior-day carryover recovery before new entries
- Duplicate-sell protection when an existing SELL is still working
- Protection of manual and unmanaged brokerage positions
- PAPER / SHADOW / LIVE runtime isolation
- No PaperBroker fallback from LIVE
- Fail-closed production activation interlock
- Zero-quantity closed broker rows excluded from active-position inventory
- Held-position priority within the kabu Station registration limit

KATANA never liquidates a Live position unless KATANA ownership can be proven. Ownership or quantity ambiguity blocks execution.

### EOD safety

The Live EOD path reserves a dedicated transition window:

```text
15:15  No new ordinary Live strategy cycle may start
15:15-15:20  Drain / transition window
15:20  Begin authoritative EOD liquidation
15:20-15:30  Reconcile and retry EOD verification
15:30  Fail closed if authoritative flatness has not been confirmed
```

This prevents a long synchronous normal Live cycle from being started immediately before EOD and delaying liquidation until after the regular cash-session close.

A still-working SELL is not automatically cancel/replaced merely to retry liquidation. This avoids duplicate submission and preserves the rule that ambiguous broker-order outcomes are never automatically retransmitted.

### Carryover recovery

If a KATANA-owned Live position remains at the broker after EOD, the next trading session uses the carryover-recovery path before permitting new entries.

Carryover handling is fail closed:

- Broker positions are read authoritatively.
- Existing orders are reconciled before another SELL is considered.
- KATANA ownership must be provable.
- Ambiguous ownership blocks execution.
- New entries remain blocked until the carryover condition is resolved according to the Live recovery policy.

## Brokerage Configuration

The following values are configuration metadata, not credentials:

```text
KATANA_LIVE_EXCHANGE=9
KATANA_LIVE_ACCOUNT_TYPE=4
KATANA_LIVE_CASH_BUY_FUND_TYPE=02
```

Never commit `.env`, API passwords, tokens, date-specific Live confirmations, databases, logs, reports containing account information, or other secrets.

## Operational Verification

Production-relevant changes should be protected by targeted regression tests plus the appropriate broader test set.

Recent EOD/carryover work includes regression coverage for Live market-session time gates, the pre-EOD drain window, EOD retry/fail-closed behavior, carryover recovery, Live position reconciliation, and closed zero-quantity broker rows.

## Key Commands

Run project Python directly from the virtual environment. Activating `Activate.ps1` is not required.

```powershell
cd C:\projects\katana

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.run_autonomous_operation_validation
```

KATANA Service:

```powershell
schtasks /Run /TN "Project KATANA Service"
schtasks /End /TN "Project KATANA Service"
```

## Technology

- Python 3.14
- FastAPI / Uvicorn
- SQLite
- pytest
- kabu Station API
- Discord
- Tailscale
- Git / GitHub
- Windows Task Scheduler

## Current Operational Priorities

1. Verify carryover recovery before new Live entries whenever a prior-day KATANA-owned position exists.
2. Verify the 15:15 pre-EOD drain window and 15:20 EOD transition under real production timing.
3. Confirm authoritative broker flatness after EOD rather than relying only on internal runtime state.
4. Continue improving strategy quality without weakening Live risk, reconciliation, or ownership controls.
5. Keep production operation autonomous: routine startup, authorization, monitoring, recovery, EOD handling, and next-business-day operation should not require manual intervention.
6. Preserve fail-closed behavior whenever broker state, ownership, order outcome, or runtime health is ambiguous.

## Git Workflow

Do not use `git add .` for production maintenance.

```powershell
git status
git diff --check
git add README.md
git commit -m "Update README for current Live operation"
git push origin main
```

Do not commit secrets, `.env`, local backup artifacts, databases, logs, generated reports, or account-specific output.

## Disclaimer

Backtest, Paper Trading, and Live Trading results do not guarantee future performance. Risk controls reduce operational risk but cannot eliminate market, execution, connectivity, or brokerage risk.
