# Project KATANA

AI-assisted Japanese equity research, backtesting, paper-trading, and automated-trading platform.

Project KATANA is a Python-based system for collecting Japanese market data,
testing trading strategies, running recoverable paper-trading sessions, and
progressively adding production-grade risk controls and operational safeguards
before live brokerage integration.

> **Current status:** v0.9 release candidate is operational and ready for the paper-trading trial.  
> Windows Task Scheduler startup, market-session gating, and Discord/LINE runtime notifications are verified.  
> **Live brokerage execution is not yet implemented.**

---

## Project goals

Project KATANA is being developed as a self-contained platform for:

- Japanese equity market-data collection
- Historical data import and persistence
- Trading-calendar management
- Strategy research and backtesting
- Strategy diagnostics and optimization
- Paper trading
- Runtime monitoring and recovery
- Risk management
- Discord and LINE operational notifications
- Future automated order execution

Safety, reproducibility, recoverability, and test coverage are prioritized
before connecting the system to a live brokerage account.

---

## Current development status

### Completed

- J-Quants market-data integration
- Trading-calendar integration
- Multi-symbol and multi-day historical imports
- Import retry and resume support
- CSV import reports
- SQLite market-data persistence
- Database schema migration support
- Five-minute bar aggregation
- Opening Range Breakout strategy
- ORB diagnostics
- Backtesting trade and exit models
- Paper broker
- Paper-broker state persistence
- Paper-broker state recovery
- Paper-trading runtime
- Runtime health monitoring
- Runtime heartbeat monitoring
- Position-sizing risk controls
- Daily-loss protection
- Consecutive-loss protection
- Kill-switch controls
- Paper-trading risk-engine integration
- Discord Webhook notifications
- LINE Messaging API notifications
- Notification templates and routing rules
- Notification Gateway
- External notification connection-test CLI
- Paper-trading start notifications
- Paper-trading completion notifications
- Paper-trading interruption and failure notifications
- Notification-failure isolation from the trading runtime
- Windows Task Scheduler installation and removal CLI
- Production-readiness check before scheduled execution
- Tokyo-market business-day and session-time gating
- Non-business-day, pre-open, and after-close skip notifications
- Runtime notification delivery diagnostics by channel
- Runtime notifications bypass quiet-hour suppression while ordinary notifications retain it
- Discord and LINE delivery verified from the scheduled market-session path
- Full regression test suite: **1,924 passing tests**

### Current milestone

**Sprint 84 completed: v0.9 paper-trading trial preparation**

The unattended startup path is now operational:

```text
Windows Task Scheduler
        |
        v
Production Readiness Check
        |
        v
Tokyo Market Session Decision
        |
   +----+-------------------+
   |                        |
   v                        v
Run Paper Trading       Skip Safely
                            |
                            v
                      Discord + LINE
```

Verified operational results:

```text
Production readiness: READY
Scheduler result:      SUCCESS
Discord delivery:      SUCCESS
LINE delivery:         SUCCESS
Regression suite:      1,924 passed, 1 warning
```

Runtime notifications use a dedicated policy that bypasses quiet-hour
suppression. Ordinary strategy and trading notifications continue to use the
configured quiet-hour rules. Channel-level delivery outcomes are written to
the runtime log for diagnosis.

### Next

The next step is the v0.9 release-candidate paper-trading trial:

- Run unattended paper trading across the next four Tokyo-market business days
- Confirm scheduled startup, safe skip, and shutdown behavior
- Review Discord and LINE notifications each day
- Review runtime logs and daily summaries
- Record warnings, failures, and operational observations
- Decide whether to promote the release candidate to v0.9

### Planned

- Extended paper-trading validation
- Operational quality and warning cleanup
- Live broker adapter
- Order reconciliation
- Production safeguards
- Unattended automated execution

---

## Architecture

The project is organized around separate domain responsibilities.

```text
Market Data
    |
    v
Repositories and Aggregation
    |
    v
Strategy
    |
    v
Trade Signal
    |
    v
Risk Management
    |
    v
Paper Broker
    |
    v
Runtime, Monitoring, Persistence, Recovery, and Notifications
```

The risk-management and notification layers are intentionally independent of
individual strategies so that the same controls can be reused by ORB and future
strategies.

---

## Main components

### Market data

The market-data layer supports:

- J-Quants data downloads
- Trading-day resolution
- Historical batch imports
- Retry and resume state
- Five-minute bar aggregation
- SQLite storage
- CSV reporting

Representative modules include:

```text
app/market/jquants_downloader.py
app/market/jquants_batch_import.py
app/market/trading_calendar.py
app/market/bar_aggregator.py
app/market/bar_repository.py
app/market/history_state.py
app/market/history_retry.py
app/import_jquants_history.py
```

### Strategy and backtesting

The current strategy implementation is Opening Range Breakout.

Supported strategy controls include:

- Opening-range end time
- Entry conditions
- Price filters
- Volume filters
- Turnover filters
- Stop loss
- Take profit
- Forced exit
- Trade diagnostics

### Risk management

Risk controls include:

- Position sizing
- Maximum number of open positions
- Maximum value per position
- Maximum value per order
- Maximum portfolio exposure
- Available buying power
- Daily-loss limits
- Consecutive-loss protection
- Kill-switch decisions
- Configurable trading lot size

Risk decisions can approve, reduce, reject, block, or stop trading activity
according to the active policy.

### Paper trading

The paper-trading subsystem provides:

- Simulated order execution
- Portfolio snapshots
- Broker equity tracking
- Persistent broker state
- Runtime restart recovery
- Runtime lifecycle management
- Safe-stop handling
- Daily runtime results

The production paper-trading launchers are:

```text
app/run_paper_trading.py
app/run_market_session.py
app/scheduler.py
```

Windows Task Scheduler integration is managed with:

```powershell
python -m app.install_scheduler
python -m app.uninstall_scheduler
```

### Runtime monitoring

Runtime monitoring includes:

- Health checks
- Runtime-state checks
- Portfolio checks
- Broker probes
- Repository probes
- Market-data freshness checks
- Heartbeat creation
- Heartbeat freshness evaluation
- Heartbeat restoration
- Resource-critical stop decisions

### Notifications

Project KATANA supports external operational notifications through:

- Discord Webhooks
- LINE Messaging API
- Notification templates
- Severity-based routing
- Quiet-hour rules
- Duplicate suppression
- Rate limiting
- Retry and exponential backoff
- Failure isolation from the trading runtime
- Channel-level delivery-result logging
- Dedicated runtime policy that bypasses quiet hours

Representative modules include:

```text
app/notification_test.py
app/notifications/notification_composition.py
app/notifications/notification_gateway.py
app/notifications/notification_rule_engine.py
app/notifications/notification_rule_service.py
app/notifications/discord_notification_channel.py
app/notifications/line/line_notification_channel.py
app/notifications/webhook_client.py
app/notifications/webhook_transport.py
```

Test external notification delivery:

```powershell
python -m app.notification_test
```

Expected output:

```text
Project KATANA Notification Test
channels=discord,line
discord: OK
line: OK
すべての通知チャネルへの送信に成功しました。
```

---

## Technology stack

- Python 3.14
- SQLite
- pytest
- J-Quants API
- Discord Webhooks
- LINE Messaging API
- Visual Studio Code
- Git and GitHub

Development is currently performed on Windows.

---

## Project structure

A simplified view of the repository:

```text
app/
├── backtest/
├── live/
├── market/
├── notifications/
│   ├── line/
│   ├── discord_notification_channel.py
│   ├── notification_composition.py
│   ├── notification_gateway.py
│   └── webhook_transport.py
├── risk/
├── runtime/
├── strategy/
├── trading/
├── database.py
├── notification_test.py
└── run_paper_trading.py

tests/
├── test_notification_composition.py
├── test_notification_test.py
├── test_run_paper_trading.py
├── test_webhook_transport.py
└── ...

README.md
```

The exact structure may evolve as later operational and broker-integration
sprints are completed.

---

## Development setup

Create and activate a virtual environment, then install the project
dependencies according to the repository configuration.

Example for Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Create a local `.env` file in the repository root for credentials and
environment-specific settings.

Example key names:

```env
KATANA_ENVIRONMENT=paper
KATANA_DISCORD_WEBHOOK_URL=...
KATANA_LINE_CHANNEL_ACCESS_TOKEN=...
KATANA_LINE_DESTINATION_ID=U...
```

Never commit the `.env` file or any real secret values.

---

## Running tests

Run the complete regression suite:

```powershell
python -m pytest -v
```

Current verified result:

```text
1924 passed, 1 warning
```

Run notification-related tests:

```powershell
python -m pytest `
    tests/test_notification_composition.py `
    tests/test_notification_test.py `
    tests/test_webhook_transport.py `
    tests/test_run_paper_trading.py `
    -v
```

A sprint is considered complete only after its relevant tests and the wider
regression suite pass.

---

## Paper-trading commands

Run the production-readiness check without starting trading:

```powershell
python -m app.run_paper_trading --check
```

Run the external notification test:

```powershell
python -m app.notification_test
```

Run the market-session-aware scheduler path:

```powershell
python -m app.scheduler
```

Run paper trading directly using the configured watch list:

```powershell
python -m app.run_paper_trading
```

Run a bounded smoke test:

```powershell
python -m app.run_paper_trading --maximum-cycles 1
```

Use `Ctrl+C` to request a safe stop.

---

## Development workflow

Project KATANA uses a safety-first workflow:

1. Implement one bounded feature.
2. Replace each changed Python file with its complete reviewed version.
3. Run the relevant tests.
4. Run the wider regression suite when appropriate.
5. Review `git status`.
6. Ensure secrets and generated artifacts are excluded.
7. Commit only after tests pass.
8. Push the reviewed commit to GitHub.

This approach reduces accidental partial edits and makes each development step
easier to review and recover.

---

## Git safety

The repository must not contain credentials or local runtime artifacts.

At minimum, `.gitignore` should exclude:

```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
reports/
data/
logs/
test_external_notifications.py
katana_sprint*.zip
```

Review staged files before every commit:

```powershell
git status
git diff --cached --name-only
```

---

## Safety notice

Project KATANA is under active development.

The current implementation is intended for research, backtesting, and paper
trading. It must not be assumed safe for unattended live trading until live
broker integration, reconciliation, kill-switch controls, operational
monitoring, and production validation are complete.

Trading involves the risk of financial loss. Strategy performance in
backtests or paper trading does not guarantee future results.

---

## Roadmap

```text
Sprint 83
Runtime notification integration — completed

Sprint 84
v0.9 paper-trading trial preparation — completed

v0.9 release-candidate trial
Four Tokyo-market business days of unattended operational validation

v0.9
Release decision after trial-log and notification review

Later sprints
Extended validation, live brokerage integration,
order reconciliation, and production safeguards
```

The roadmap may be adjusted as testing reveals new safety or architectural
requirements.
