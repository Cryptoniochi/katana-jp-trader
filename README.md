# Project KATANA

Automated Japanese equity trading platform for market-data collection, strategy execution, risk control, Paper Trading, monitoring, reporting, and fail-closed Live Trading.

## Current Status — 2026-10-23

- Git baseline: use `git log -1 --oneline` for the current committed revision
- Repository test suite: **3,500+ tests**; run the full suite before each production-relevant commit
- Current mode: **Paper Trading**
- Trading capital: **JPY 1,000,000**
- Market universe: approximately **3,700** domestic common stocks
- Realtime watchlist: maximum **50** symbols
- Market data: kabu Station REST / WebSocket and 5-minute bars
- J-Quants is not required by the active runtime
- Live Trading implementation and brokerage commissioning are complete
- **Live production activation remains OFF**

The current priority is strategy validation. Live Trading will remain disabled until Paper Trading performance is satisfactory.

## Strategies

- Opening Range Breakout v2 (ORB)
- Pullback Breakout
- High Breakout

Current ORB Paper/production strategy filter:

```text
breakout-bar volume >= 0.8 x average opening-range bar volume
minimum breakout width >= 0.5%
```

The 0.5% breakout-width filter was selected after robustness testing across the available 5-minute-bar history. It materially improved net P/L and drawdown versus the previous volume-only baseline and remained positive after excluding the strongest day.

Protective stop-loss: **1%**
Take-profit: **2%**

## Recent Paper Trading Performance

Observation period: **2026-10-19 through 2026-10-23**

| Date | Trades | W-L-Flat | Net P/L | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-19 | 9 | 4-3-2 | +10,700 JPY | 4.45 |
| 2026-10-20 | 8 | 4-4-0 | +5,450 JPY | 2.14 |
| 2026-10-21 | 8 | 1-7-0 | -5,950 JPY | 0.14 |
| 2026-10-22 | 3 | 0-3-0 | -4,450 JPY | 0.00 |
| 2026-10-23 | 7 | 1-6-0 | -4,200 JPY | 0.22 |
| **Total** | **35** | **10-23-2** | **+1,550 JPY** | **1.06** |

Five-day aggregate:

- Gross profit: **+26,250 JPY**
- Gross loss: **-24,700 JPY**
- Average win: **+2,625 JPY**
- Average loss: **-1,074 JPY**
- Payoff ratio: **2.44**
- Expectancy: **+44 JPY/trade**
- Peak-to-trough trade-level drawdown: approximately **-15,800 JPY**
- ORB: **32 trades / +5,400 JPY**
- Pullback: **3 trades / -3,850 JPY**
- High Breakout: **0 completed trades before the 2026-10-23 screening-path repair**

The first two days produced +16,150 JPY, while the final three days lost 14,600 JPY. The week therefore remained slightly profitable but was not strong enough to justify enabling Live Trading.

### ORB robustness work

The previous ORB filter used only a 0.8x opening-range volume requirement. Analysis showed that simply increasing the volume threshold was insufficient. A minimum breakout width was more effective.

The selected Paper Trading configuration for the next observation period is:

```text
volume ratio >= 0.8
minimum breakout width >= 0.5%
stop loss = 1%
take profit = 2%
```

Across 19 eligible historical sessions, the selected configuration produced **+469,003 JPY**, PF **2.81**, and materially lower drawdown than the previous 0.8x volume-only baseline. Excluding the strongest day, it still produced **+216,323 JPY** with PF **1.83**.

This remains a Paper Trading validation candidate, not evidence that future returns are guaranteed.

### High Breakout repair

High Breakout had been screening only the 50-symbol realtime Dynamic Watchlist. The screening path was repaired so that High Breakout can evaluate the full daily-market universe while realtime registration remains capped at 50 symbols.

The repaired production-path screening for the 2026-10-26 trading date produced **26 candidates** without loosening the strategy thresholds.

### Paper Trading state repair

A Paper Trading state bug was also repaired: when a BUY signal was rejected before an actual fill, the strategy could incorrectly retain `position_open=True` and later emit an invalid SELL. The strategy position state is now closed after an unfilled BUY while same-day re-entry protection is retained.

## Risk Controls

- Maximum positions: **20**
- Maximum daily entries: **20**
- Maximum daily loss: **JPY 20,000**
- Maximum value per symbol: **JPY 1,000,000**
- Maximum total exposure: **JPY 5,000,000**
- Minimum cash: **JPY 500,000**
- Protective stop-loss: **1%**

Risk, reconciliation, position-ownership, and EOD controls fail closed.

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

## Autonomous Operation

KATANA runs as a resident Windows task.

```text
08:40  Morning Pre-Flight
08:45  Runtime start
09:00  Morning session
11:30  Lunch break
12:30  Afternoon session
15:30  Market close / EOD processing
15:35  Runtime stop
15:40  Daily Report
```

KATANA Service manages:

- Dashboard
- Dynamic Watchlist Scheduler
- Universe Daily Scheduler
- Morning Pre-Flight Scheduler
- Trading Scheduler
- Daily Report Scheduler
- Recovery and health monitoring

## Live Trading

The complete Live execution path has been implemented and commissioned against the real brokerage account, including a confirmed BUY and SELL round trip.

A concrete Paper-free production composition now exists. It connects realtime market data, the strategy engine, authoritative brokerage account state, Live risk controls, durable execution/reconciliation, protective exits, and EOD liquidation.

**Live production activation remains deliberately OFF.**

Historical Live locks remain sealed and must not be changed:

```text
LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = False
LIVE_BROKER_TRANSPORT_ENABLED = False
LIVE_ORDER_TRANSMISSION_ENABLED = False
```

Concrete Live production uses a separate activation interlock:

```text
KATANA_LIVE_PRODUCTION_ENABLED=YES
```

Daily Live operation additionally requires explicit daily arming and date-specific confirmation. These activation variables remain unset during the current Paper Trading period.

Implemented Live safeguards include:

- Authoritative brokerage account and position reads
- Durable order and reconciliation state
- No automatic retry after ambiguous order transmission
- Durable daily entry limits
- Protective-stop persistence and restart recovery
- EOD liquidation with position-ownership verification
- Protection of manual and unmanaged brokerage positions
- PAPER / SHADOW / LIVE runtime isolation
- No PaperBroker fallback from LIVE
- Fail-closed production activation interlock

KATANA never liquidates a live position unless KATANA ownership can be proven. Ownership or quantity ambiguity blocks execution.

Verified account mapping:

```text
KATANA_LIVE_EXCHANGE=27
KATANA_LIVE_ACCOUNT_TYPE=4
KATANA_LIVE_CASH_BUY_FUND_TYPE=02
```

Never commit `.env`, API passwords, tokens, or other secrets.

## Key Commands

Run project Python directly from the virtual environment. Activating `Activate.ps1` is not required.

```powershell
cd C:\projects\katana

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.run_paper_trading --check
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
- LINE
- Tailscale
- Git / GitHub
- Windows Task Scheduler

## Next Steps

1. Run Paper Trading on **2026-10-26** with the new ORB `0.8x volume + 0.5% breakout width` filter.
2. Verify that the repaired High Breakout candidate path produces actual strategy/Risk Gate/PaperBroker activity from the 26 screened candidates.
3. Confirm that alphanumeric JPX codes such as `277A` / `549A` remain valid through the complete Paper Trading path.
4. Continue collecting Pullback trades after the unfilled-BUY state repair before changing Pullback parameters.
5. Compare the new ORB Paper results with the 2026-10-19 through 2026-10-23 baseline.
6. Change strategy parameters only when supported by accumulated out-of-sample Paper Trading evidence.
7. Keep Live production activation OFF until Paper Trading performance is satisfactory.

## Git Workflow

```powershell
git status
git diff --check
git add README.md
git commit -m "Update README to current KATANA status"
git push origin main
```

Avoid `git add .`.

Do not commit secrets, databases, logs, generated reports, or local backup artifacts.

## Disclaimer

Backtest and Paper Trading results do not guarantee future performance. Live Trading is technically available but remains intentionally disabled while strategy performance is being validated.
