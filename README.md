# Project KATANA

AI-assisted Japanese equity research, backtesting, paper-trading, risk-control,
operations, monitoring, and multi-strategy development platform.

> **Current status:** Sprint104-5 / Version 1.0 RC operational baseline.
> The production paper-trading runtime uses the kabuステーションAPI for realtime market data.
> J-Quants is no longer required by the active runtime.
> Live brokerage execution is not implemented.

---

## Current capabilities

### Market data and persistence

- kabuステーション REST and WebSocket integration
- Realtime market monitoring
- Five-minute bar persistence in SQLite
- Intraday-to-daily bar aggregation
- Tokyo-market calendar and market-session gating
- High Breakout daily-candidate screening and persistence
- Production watchlist limited to 50 symbols

### Trading strategies

```text
ORB
Pullback Breakout
High Breakout
```

The Strategy Registry resolves same-bar duplication and contradictory signals
before forwarding them to the trading and risk layers.

### Paper trading and risk

- Recoverable Paper Broker
- Production Paper Trading runtime
- Pre-trade Risk Gate
- Position-count, position-value, exposure, cash, daily-loss, and entry limits
- Signal → Risk → Broker JSONL trace
- Runtime health, heartbeat, recovery, and safe-stop handling
- Discord and LINE operational notifications
- Production Readiness check
- Autonomous Operation Validator
- Scheduler Guard before Paper Trading startup

### Autonomous operation

Project KATANA runs as a resident Windows task through KATANA Service.

```text
Windows logon
    |
    v
Project KATANA Service
    |
    +-- Dashboard
    +-- Morning Pre-Flight Scheduler
    +-- Paper Trading Scheduler
    +-- Daily Report Scheduler
    +-- Recovery / health monitoring
```

Standard schedule:

```text
08:40  Morning Pre-Flight validation and notification
08:45  Paper Trading Scheduler start window
09:00  Morning market session
11:30  Lunch break
12:30  Afternoon market session
15:30  Market close
15:35  Paper Trading stop
15:40  Daily Report generation and LINE / Discord notification
```

Expected Service topology:

```text
dashboard                    enabled / running
morning_preflight_scheduler  enabled / running
daily_report_scheduler       enabled / running
paper_trading_scheduler      enabled / running
paper_trading                disabled
```

The direct `paper_trading` component remains disabled to prevent duplicate
runtime startup.

### Dashboard and reporting

- Desktop and mobile FastAPI Dashboard
- Service component status and PID monitoring
- Recovery History
- Today's Paper Trading schedule
- Morning Check panel
- Operational Readiness panel
- Daily Report panel
- Strategy and symbol ranking
- Error and recovery counts

Dashboard URLs:

```text
Desktop on KATANA PC:
http://127.0.0.1:8000/

Mobile through Tailscale:
http://100.64.14.23:8000/mobile
```

The Dashboard is exposed through the private Tailscale network, not through
public router port forwarding.

### Morning Pre-Flight

Checks:

```text
KATANA Service
Service component topology
Paper Trading Scheduler
Daily Report Scheduler
Watchlist
Database
Production Readiness
```

Files:

```text
reports/service/autonomous_operation_report.json
reports/service/morning_preflight_schedule.json
reports/service/morning_preflight/YYYY-MM-DD.sent.json
```

### Daily Report

Daily Reports include:

```text
Report date
Net P/L
Trade count
Win rate
Profit Factor
Maximum drawdown
Strategy ranking
Symbol ranking
Errors
Recoveries
Notes
```

Files:

```text
reports/daily/YYYY-MM-DD.json
reports/daily/notifications/YYYY-MM-DD.sent.json
```

---

## Current milestone

### Completed through Sprint104-5

- Sprint95: Desktop and Mobile Dashboard baseline
- Sprint96-99: operations, recovery, and service-readiness foundations
- Sprint100: KATANA Service Windows-task migration
- Sprint101: Paper Trading schedule and readiness integration
- Sprint102: Daily Report generation, API, Dashboard, notifications, and scheduled delivery
- Sprint103: Paper Trading Scheduler integration and Production Readiness
- Sprint104:
  - Autonomous Operation Validator
  - Morning Pre-Flight notification
  - Scheduler Guard
  - Automated Morning Pre-Flight Scheduler
  - Morning Check Dashboard

Recent focused test results:

```text
Sprint102-5A: 5 passed
Sprint102-6: 19 passed
Sprint103-1: 10 passed
Sprint104-1: 3 passed
Sprint104-2: 7 passed
Sprint104-3: 10 passed
Sprint104-4: 12 passed
```

Focused suites may overlap and must not be added together as a unique
repository-wide test total.

---

## Technology stack

- Python 3.14
- FastAPI and Uvicorn
- SQLite
- pytest
- kabuステーションAPI
- Discord Webhooks
- LINE Messaging API
- Tailscale
- Visual Studio Code
- Git and GitHub
- Windows Task Scheduler
- Windows

J-Quants is no longer part of the production runtime.

---

## Important commands

### Activate the environment

```powershell
cd C:\projects\katana
.\.venv\Scripts\Activate.ps1
```

### Production Readiness

```powershell
python -m app.run_paper_trading --check
```

Expected:

```text
Overall
READY
```

### Autonomous-operation validation

```powershell
python -m app.run_autonomous_operation_validation
```

Expected:

```text
Overall: READY
Ready for next business day: True
```

### Morning Pre-Flight

```powershell
python -m app.run_morning_preflight --dry-run
python -m app.run_morning_preflight
```

### KATANA Service Dry Run

```powershell
python -m app.run_katana_service --dry-run
```

Expected topology:

```text
dashboard: enabled=True
morning_preflight_scheduler: enabled=True
daily_report_scheduler: enabled=True
paper_trading_scheduler: enabled=True
paper_trading: enabled=False
```

### Start and stop KATANA Service

```powershell
schtasks /Run /TN "Project KATANA Service"
schtasks /End /TN "Project KATANA Service"
```

Resident task command:

```text
scripts\run_katana_service_task.cmd
```

It must include:

```text
--enable-morning-preflight-schedule
--enable-daily-report-schedule
--enable-paper-trading-schedule
```

### Inspect status

```powershell
Get-Content reports\service\katana_service_status.json
Get-Content reports\service\morning_preflight_schedule.json
Get-Content reports\service\paper_trading_schedule.json
Get-Content reports\service\daily_report_schedule.json
```

### Dashboard checks

```powershell
netstat -ano | findstr :8000
Invoke-RestMethod http://100.64.14.23:8000/api/dashboard/morning-preflight
```

### Manual Paper Trading

```powershell
python -m app.run_paper_trading `
  --strategy orb `
  --strategy pullback `
  --strategy high-breakout
```

### Daily Report

```powershell
python -m app.run_daily_report --report-date 2026-08-01

python -m app.run_daily_report_notification `
  --report-date 2026-08-01 `
  --dry-run

python -m app.run_daily_report_notification `
  --report-date 2026-08-01
```

---

## Environment variables

```env
KATANA_ENVIRONMENT=paper
KABU_STATION_API_PASSWORD=...
KATANA_MARKET_DATA_MODE=kabu-station-realtime
KATANA_ENABLED_STRATEGIES=orb,pullback,high-breakout
KATANA_DISCORD_WEBHOOK_URL=...
KATANA_LINE_CHANNEL_ACCESS_TOKEN=...
KATANA_LINE_DESTINATION_ID=U...
```

Never commit `.env` or any real secret.

---

## Git workflow

```powershell
git status
git add .
git diff --cached --name-only
git commit -m "Sprint104-5: complete autonomous operations dashboard"
git push origin main
```

Before committing, verify that `.gitignore` covers:

```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
reports/
data/
logs/
katana_sprint*.zip
```

Do not commit secrets, local databases, logs, generated reports, or Sprint ZIP
archives.

---

## Current next steps

1. Commit and push the verified Sprint104-5 baseline.
2. Restart the PC and verify automatic KATANA Service startup.
3. Verify the complete schedule on the next Tokyo-market business day.
4. Run Paper Trading for multiple business days.
5. Review strategy performance before changing capital allocation.
6. Continue Version 1.0 release validation and recovery drills.

---

## Safety notice

Project KATANA remains a research and paper-trading system.

Live brokerage execution, live-account order reconciliation, and production
live-trading safeguards are not implemented. Backtest and paper-trading results
do not guarantee future performance, and trading involves the risk of loss.
