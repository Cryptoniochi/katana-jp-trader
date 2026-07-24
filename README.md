# Project KATANA

AI-assisted Japanese equity research, backtesting, paper-trading, and automated-trading platform.

Project KATANA is a Python-based system for collecting Japanese market data,
testing trading strategies, running recoverable paper-trading sessions, and
progressively adding production-grade risk controls and operational safeguards
before live brokerage integration.

> **Current status:** v0.9.1 paper-trading baseline is operational and ready for an unattended trial.  
> Windows Task Scheduler startup, market-session gating, Discord/LINE runtime notifications,
> daily summaries, J-Quants rate-limit protection, and round-robin market-data polling are verified.  
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
- Safe unattended scheduling
- Future automated order execution

Safety, reproducibility, recoverability, observability, and test coverage are
prioritized before connecting the system to a live brokerage account.

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
- Daily paper-trading summary notifications
- Notification-failure isolation from the trading runtime
- Windows Task Scheduler installation and removal CLI
- Production-readiness check before scheduled execution
- Tokyo-market business-day and session-time gating
- Non-business-day, pre-open, and after-close skip notifications
- Runtime notification delivery diagnostics by channel
- Runtime notifications bypass quiet-hour suppression while ordinary notifications retain it
- Discord and LINE delivery verified from the scheduled market-session path
- Paper-trading cycle failure diagnostics
- J-Quants HTTP 429 rate-limit detection
- J-Quants `Retry-After` handling
- Rate-limit cooldown handling without stopping the runtime
- Round-robin symbol polling
- Configurable maximum symbols per poll
- Reduced J-Quants API load for 100-symbol paper trading
- Full regression test suite: **1,938 passing tests**

### Current milestone

**Sprint 86-2 completed: J-Quants rate-limit protection and polling optimization**

The unattended paper-trading path is now:

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
   |                        |
   v                        v
Round-Robin Polling     Discord + LINE
   |
   v
J-Quants Rate-Limit Protection
   |
   v
Strategy, Risk, Paper Broker,
Persistence, Daily Summary,
Discord, and LINE
```

Verified operational results:

```text
Production readiness:         READY
Scheduler result:              SUCCESS
Discord delivery:              SUCCESS
LINE delivery:                 SUCCESS
Sprint 86-2 focused tests:     55 passed
Regression suite:              1,938 passed, 1 warning
```

Runtime notifications use a dedicated policy that bypasses quiet-hour
suppression. Ordinary strategy and trading notifications continue to use the
configured quiet-hour rules. Channel-level delivery outcomes are written to
the runtime log for diagnosis.

The paper-trading runtime also records the most frequent cycle-failure causes.
This diagnostic identified repeated J-Quants HTTP 429 responses as the cause
of earlier failed cycles. The runtime summary itself was operating correctly.

### Current J-Quants polling policy

The default production settings are:

```text
Maximum symbols per poll:       10
Rate-limit cooldown:            60 seconds
Paper-trading cycle interval:   30 seconds
Market-data interval:           5 minutes
```

With a 100-symbol watch list, the runtime polls symbols in round-robin batches
of 10. Under a 30-second runtime cycle, all 100 symbols are visited in
approximately five minutes.

When J-Quants returns HTTP 429:

- the error is identified structurally by HTTP status
- `Retry-After` is used when provided
- otherwise the configured cooldown is used
- provider calls are paused during cooldown
- the runtime remains active
- non-429 download errors continue to propagate as ordinary failures

### Next

The next step is an unattended v0.9.1 paper-trading validation period:

- Run paper trading for approximately one Tokyo-market week
- Keep the 100-symbol watch list enabled
- Confirm scheduled startup, safe skip, and shutdown behavior
- Review Discord and LINE notifications each day
- Review runtime logs and daily summaries
- Confirm the HTTP 429 count is substantially reduced
- Record API waiting periods, warnings, failures, and operational observations
- Confirm BUY, SELL, and EXIT notification delivery
- Decide whether further polling optimization is required
- Decide whether to promote the baseline toward v0.9 release

### Planned

- Extended paper-trading validation
- Operational quality and warning cleanup
- Market-data polling metrics
- Daily Summary observability improvements
- API-call and rate-limit statistics
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

The real-time market-data path is:

```text
PaperTradingComposition
        |
        v
RealtimeMarketMonitor
        |
        v
Round-Robin Symbol Selection
        |
        v
JQuantsMinuteDownloader
        |
        v
HTTP 429 Detection and Cooldown
        |
        v
Bar Aggregation and Repository
```

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
- Real-time symbol polling
- Round-robin watch-list traversal
- Configurable per-poll symbol limits
- J-Quants HTTP 429 handling
- `Retry-After` parsing
- Rate-limit cooldowns

Representative modules include:

```text
app/market/jquants_downloader.py
app/market/jquants_batch_import.py
app/market/trading_calendar.py
app/market/bar_aggregator.py
app/market/bar_repository.py
app/market/history_state.py
app/market/history_retry.py
app/market/realtime_market_service.py
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
- Cycle success and failure counting
- Frequent failure-cause diagnostics
- Rate-limit-safe continuation
- Configurable symbol polling limits

The production paper-trading launchers are:

```text
app/run_paper_trading.py
app/run_market_session.py
app/scheduler.py
```

The production composition root is:

```text
app/runtime/paper_trading_composition.py
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
- Cycle-failure diagnostics
- Daily runtime summaries

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
- Runtime start and completion notifications
- Runtime interruption and failure notifications
- BUY, SELL, and EXIT notifications
- Daily paper-trading summaries

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
│   ├── jquants_downloader.py
│   ├── realtime_market_service.py
│   └── ...
├── notifications/
│   ├── line/
│   ├── discord_notification_channel.py
│   ├── notification_composition.py
│   ├── notification_gateway.py
│   └── webhook_transport.py
├── risk/
├── runtime/
│   ├── paper_trading_composition.py
│   └── ...
├── strategy/
├── trading/
├── database.py
├── notification_test.py
├── run_market_session.py
├── run_paper_trading.py
└── scheduler.py

tests/
├── test_jquants_downloader.py
├── test_realtime_market_service.py
├── test_paper_trading_composition.py
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
JQUANTS_API_KEY=...
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
1938 passed, 1 warning
```

Run the Sprint 86-2 focused tests:

```powershell
python -m pytest `
    tests/test_jquants_downloader.py `
    tests/test_realtime_market_service.py `
    tests/test_paper_trading_composition.py `
    -v
```

Current verified focused result:

```text
55 passed
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

## Paper-trading validation checklist

During the v0.9.1 trial, review the following each market day:

```text
[ ] Windows Task Scheduler started the process
[ ] Production readiness returned READY
[ ] Market-session decision was correct
[ ] Runtime start notification arrived
[ ] Discord delivery succeeded
[ ] LINE delivery succeeded
[ ] Runtime remained active through the expected session
[ ] BUY/SELL/EXIT notifications were correct when signals occurred
[ ] Daily Summary arrived
[ ] Success and failure cycle counts were plausible
[ ] J-Quants 429 count was reduced
[ ] No repeated API hammering occurred during cooldown
[ ] Runtime completed or stopped safely
[ ] Logs contain no unexplained exceptions
```

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
9. Tag stable paper-trading baselines when appropriate.

This approach reduces accidental partial edits and makes each development step
easier to review and recover.

---

## Git checkpoint for Sprint 86-2

Review changes:

```powershell
git status
git diff --stat
git diff --cached --name-only
```

Stage the completed files:

```powershell
git add .
```

Commit the verified baseline:

```powershell
git commit -m "Sprint86-2: add J-Quants rate-limit protection and round-robin polling"
```

Push the current branch:

```powershell
git push origin main
```

Create a stable baseline tag:

```powershell
git tag -a v0.9.1 -m "Stable paper-trading baseline with J-Quants rate-limit protection"
git push origin v0.9.1
```

Confirm the actual branch name before pushing if the repository does not use
`main`.

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
git diff --cached
```

Do not commit:

- API keys
- Discord webhook URLs
- LINE access tokens
- LINE destination IDs
- local databases
- local logs
- generated reports
- notification-test secrets
- sprint ZIP archives

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

Sprint 85
Paper-trading trial start and watch-list expansion — completed

Sprint 86-1
Runtime cycle-failure diagnostics — completed

Sprint 86-2
J-Quants HTTP 429 protection,
Retry-After handling,
cooldown control,
and round-robin polling — completed

v0.9.1 validation
Approximately one Tokyo-market week of unattended paper trading

Next operational sprint
Analyze trial logs, API usage, 429 frequency,
daily summaries, and notification reliability

v0.9
Release decision after trial validation

Later sprints
Extended validation, live brokerage integration,
order reconciliation, and production safeguards
```

The roadmap may be adjusted as testing reveals new safety or architectural
requirements.
