# Project KATANA

Automated Japanese equity trading platform for market-data collection, strategy execution, risk control, Paper Trading, monitoring, reporting, and fail-closed Live Trading.

## Current Status ? 2026-10-21

- Git baseline: `24c47aa` ? `Protect unmanaged live positions from EOD liquidation`
- Repository tests: **3,513 passed, 2 warnings**
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

Current ORB production filter:

```text
breakout-bar volume >= 0.8 x average opening-range bar volume
```

Protective stop-loss: **1%**

## Recent Paper Trading Performance

| Date | Trades | W-L-Flat | Net P/L | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-19 | 9 | 4-3-2 | +10,700 JPY | 4.45 |
| 2026-10-20 | 8 | 4-4-0 | +5,450 JPY | 2.14 |
| 2026-10-21 | 8 | 1-7-0 | -5,950 JPY | 0.14 |
| **Total** | **25** | **9-14-2** | **+10,200 JPY** | **1.69** |

The current configuration will remain unchanged through the observation week. Strategy changes will be made only when supported by accumulated trading data.

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

Production activation remains deliberately disabled.

Historical Live locks remain sealed:

```text
LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = False
LIVE_BROKER_TRANSPORT_ENABLED = False
LIVE_ORDER_TRANSMISSION_ENABLED = False
```

Live production uses a separate activation gate and daily arming mechanism.

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

KATANA never liquidates a live position unless KATANA ownership can be proven. Ownership or quantity ambiguity blocks execution.

Verified account mapping:

```text
KATANA_LIVE_EXCHANGE=27
KATANA_LIVE_ACCOUNT_TYPE=4
KATANA_LIVE_CASH_BUY_FUND_TYPE=02
```

During the current Paper Trading period, Live activation variables remain unset.

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

1. Continue unchanged Paper Trading through the observation week.
2. Evaluate weekly P/L, win rate, Profit Factor, average win/loss, and drawdown.
3. Compare winning and losing ORB trades by volume ratio, breakout width, entry time, and price range.
4. Investigate why Pullback signals are not appearing as completed trades in the Daily Report.
5. Review High Breakout candidate and execution frequency.
6. Adjust strategy filters only when supported by accumulated data.
7. Keep Live production activation OFF until performance is satisfactory.

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
