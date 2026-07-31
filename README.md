# Project KATANA

AI-assisted Japanese equity research, backtesting, paper-trading, risk-control,
operations, and multi-strategy development platform.

> **Current status:** Sprint95-2A development baseline.
> The paper-trading runtime uses the kabuステーションAPI for realtime market data.
> J-Quants is no longer required by the production runtime.
> Live brokerage execution is not implemented.

---

## Current capabilities

### Market data and persistence

- kabuステーション REST and WebSocket integration
- Realtime market monitoring
- Five-minute bar persistence in SQLite
- Intraday-to-daily bar aggregation
- Tokyo-market calendar and market-session gating
- Historical CSV input where required
- High Breakout daily-candidate screening
- High Breakout candidate persistence and reports

### Trading strategies

Project KATANA currently supports three strategies through Strategy Registry:

```text
ORB
Pullback Breakout
High Breakout
```

The Registry safely resolves same-bar signal duplication and contradictory
signals before forwarding them to the trading and risk layers.

### Paper trading and risk

- Recoverable paper broker
- Paper-trading runtime
- Pre-trade Risk Gate
- Position-count, position-value, exposure, cash, daily-loss, and entry limits
- Deterministic Risk Gate proof scenarios
- Signal → Risk → Broker JSONL trace
- Runtime health, heartbeat, recovery, and safe-stop handling
- Discord and LINE operational notifications

### Analytics and Dashboard

- Strategy Analytics in JSON, CSV, and HTML
- Strategy-level signal, execution, trade, win-rate, Profit Factor, P/L,
  holding-time, and drawdown metrics
- Existing FastAPI Operations Dashboard
- Strategy Summary and Recent Trades panels
- Desktop Dashboard
- Mobile-optimized Dashboard page

Dashboard URLs on the KATANA PC:

```text
Desktop: http://127.0.0.1:8000/
Mobile:  http://127.0.0.1:8000/mobile
```

The standard Dashboard is intentionally **local-only**. LAN exposure,
router port forwarding, and Windows Firewall exceptions are not part of the
supported default configuration. Remote access may be added later through a
private VPN such as Tailscale.

### High Breakout pipeline

```text
Saved intraday bars
        |
        v
Daily-bar aggregation
        |
        v
20-day / 60-day / year-to-date screening
        |
        v
High Breakout candidate repository
        |
        v
CSV / JSON / HTML reports
        |
        v
Five-minute realtime confirmation
        |
        v
Risk Gate and Paper Broker
```

The current database contains only the history accumulated locally.
A 60-day breakout requires at least 60 trading days of stored daily bars.

---

## Current milestone

### Completed through Sprint95-2A

- Sprint88: previous-day replay diagnostics
- Sprint89–90: market-data provider abstraction and kabuステーション integration
- Sprint91: production paper trading, Risk Gate, proof suite, and trace
- Sprint92: production-runtime J-Quants dependency removal
- Sprint93: Strategy Registry, Pullback Breakout, and Strategy Analytics
- Sprint94: High Breakout screener, repository, CLI, realtime strategy,
  daily-bar builder, and operation runner
- Sprint95-1: existing Dashboard strategy extension
- Sprint95-2: mobile Dashboard page
- Sprint95-2A: local-only Dashboard policy restored

Recent verified focused results include:

```text
Sprint93-2: 117 passed
Sprint93-3: 38 passed
Sprint94-1A: 21 passed
Sprint94-1B: 28 passed
Sprint94-1C: 25 passed
Sprint94-2: 110 passed
Sprint94-3: 9 passed
Sprint94-4: 11 passed
Sprint95-1: 19 passed, 1 warning
```

Test totals above are focused suites and overlap. They must not be added
together as a repository-wide unique test count.

---

## Architecture

```text
kabuステーション API
        |
        v
Realtime Market Provider
        |
        v
MarketBarRepository
        |
        +--------------------------+
        |                          |
        v                          v
Five-minute strategies       Daily-bar aggregation
        |                          |
        |                          v
        |                    High Breakout Screener
        |                          |
        |                          v
        |                    Candidate Repository
        |                          |
        +------------+-------------+
                     |
                     v
              Strategy Registry
                     |
                     v
                 Signals
                     |
                     v
                 Risk Gate
                     |
                     v
                Paper Broker
                     |
        +------------+-------------+
        |            |             |
        v            v             v
      Trace       Analytics     Dashboard
```

---

## Technology stack

- Python 3.14
- FastAPI and Uvicorn
- SQLite
- pytest
- kabuステーションAPI
- Discord Webhooks
- LINE Messaging API
- Visual Studio Code
- Git and GitHub
- Windows

J-Quants is no longer part of the production runtime. Legacy J-Quants modules
may remain in historical, migration, or archived areas until a later cleanup,
but the active realtime paper-trading path does not require a J-Quants API key.

---

## Important commands

### Activate the environment

```powershell
cd C:\projects\katana
.\.venv\Scripts\Activate.ps1
```

### Run production-readiness checks

```powershell
python -m app.run_paper_trading --check
```

### Run paper trading

ORB only:

```powershell
python -m app.run_paper_trading --strategy orb
```

Pullback only:

```powershell
python -m app.run_paper_trading --strategy pullback
```

High Breakout only:

```powershell
python -m app.run_paper_trading --strategy high-breakout
```

All strategies:

```powershell
python -m app.run_paper_trading `
  --strategy orb `
  --strategy pullback `
  --strategy high-breakout
```

### Build daily bars

```powershell
python -m app.run_build_daily_bars
```

### Run High Breakout screening

```powershell
python -m app.run_high_breakout_screening
```

### Run the High Breakout operation pipeline

```powershell
python -m app.run_high_breakout_operation
```

### Generate Strategy Analytics

```powershell
python -m app.run_strategy_analytics
```

### Start the Dashboard

```powershell
python -m app.dashboard `
  --host 127.0.0.1 `
  --database data\katana.db
```

Desktop:

```text
http://127.0.0.1:8000/
```

Mobile layout on the PC:

```text
http://127.0.0.1:8000/mobile
```

The mobile layout is retained for future secure remote-access integration, but
the default Dashboard is not exposed to the local network or public Internet.

### Test external notifications

```powershell
python -m app.notification_test
```

---

## Environment variables

Example names:

```env
KATANA_ENVIRONMENT=paper
KABU_STATION_API_PASSWORD=...
KATANA_MARKET_DATA_MODE=kabu-station-realtime
KATANA_ENABLED_STRATEGIES=orb
KATANA_DISCORD_WEBHOOK_URL=...
KATANA_LINE_CHANNEL_ACCESS_TOKEN=...
KATANA_LINE_DESTINATION_ID=U...
```

Never commit `.env` or any real secret.

`JQUANTS_API_KEY` is no longer required by the production runtime.

---

## Development workflow

1. Implement one bounded Sprint.
2. Replace modified Python files with complete reviewed versions.
3. Run focused tests.
4. Run the wider regression suite when appropriate.
5. Review `git status` and staged content.
6. Keep secrets, SQLite databases, reports, logs, and Sprint ZIP files out of Git.
7. Commit only after tests pass.
8. Push the reviewed commit to GitHub.

Recommended checkpoint for this update:

```powershell
git status
git add .
git diff --cached --name-only
git commit -m "Sprint95-2A: extend dashboard and restore local-only access"
git push origin main
```

---

## Git safety

At minimum, `.gitignore` should cover:

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

Do not commit:

- kabuステーションAPI passwords
- Discord webhook URLs
- LINE access tokens or destination IDs
- local SQLite databases
- logs and generated reports
- Sprint ZIP archives

---

## Current next steps

1. Apply Sprint95-2A and run the Dashboard tests.
2. Open the local Desktop and Mobile layouts on the KATANA PC.
3. Commit and push the verified files to GitHub.
4. Continue Sprint95 with Trade Journal and strategy-performance enhancements.
5. Add secure remote access only when it is operationally needed.

---

## Safety notice

Project KATANA remains a research and paper-trading system.

Live brokerage execution, order reconciliation, live-account safeguards, and
production validation are not complete. Backtest and paper-trading results do
not guarantee future performance, and trading involves the risk of loss.
