# Project KATANA

AI-assisted Japanese equity research, backtesting, and automated trading platform.

Project KATANA is a Python-based system for collecting Japanese market data,
testing trading strategies, running recoverable paper trading sessions, and
progressively adding production-grade risk controls before live brokerage
integration.

> **Current status:** Paper-trading infrastructure is operational.  
> Live brokerage execution is not yet implemented.

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

### In progress

Sprint 77: Risk Management Engine

- [x] Position sizing
- [ ] Daily loss limit
- [ ] Consecutive-loss protection
- [ ] Kill switch
- [ ] Risk report

### Planned

- Paper-trading risk-engine integration
- Operational quality and warning cleanup
- Beta milestone
- Live broker adapter
- Order reconciliation
- Production safeguards
- Automated execution

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
Runtime, Monitoring, Persistence, and Recovery
```

The risk-management layer is intentionally independent of individual
strategies so that the same controls can be reused by ORB and future
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

### Paper trading

The paper-trading subsystem provides:

- Simulated order execution
- Portfolio snapshots
- Broker equity tracking
- Persistent broker state
- Runtime restart recovery
- Runtime lifecycle management

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

### Risk management

The first completed risk-control component is position sizing.

Current position-sizing constraints include:

- Maximum number of open positions
- Maximum value per position
- Maximum value per order
- Maximum portfolio exposure
- Available buying power
- Configurable trading lot size

Each sizing request returns one of:

```text
APPROVED
REDUCED
REJECTED
```

Relevant modules:

```text
app/risk/position_sizing_models.py
app/risk/position_sizing_service.py
tests/test_position_sizing_service.py
```

The position-sizing test suite currently contains 27 passing tests.

---

## Technology stack

- Python 3.14
- SQLite
- pytest
- J-Quants API
- Visual Studio Code
- Git

Development is currently performed on Windows.

---

## Project structure

A simplified view of the repository:

```text
app/
├── backtest/
├── market/
├── risk/
│   ├── position_sizing_models.py
│   └── position_sizing_service.py
├── runtime/
├── strategy/
├── trading/
├── database.py
└── import_jquants_history.py

tests/
├── test_position_sizing_service.py
├── test_runtime_health_service.py
├── test_runtime_heartbeat_service.py
└── ...

README.md
```

The exact structure may evolve as later risk-management and broker-integration
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

Configure the required J-Quants credentials and local database settings before
running data-import commands.

Do not commit secrets, API credentials, access tokens, or private account
information to Git.

---

## Running tests

Run the complete test suite:

```powershell
python -m pytest
```

Run the position-sizing tests:

```powershell
python -m pytest tests/test_position_sizing_service.py -v
```

Run runtime monitoring tests:

```powershell
python -m pytest tests/test_runtime_health_service.py `
    tests/test_runtime_heartbeat_service.py -v
```

A sprint is considered complete only after its tests pass.

---

## Development workflow

Project KATANA uses a safety-first workflow:

1. Implement one bounded feature.
2. Replace each changed Python file with its complete reviewed version.
3. Run the relevant tests.
4. Run the wider regression suite when appropriate.
5. Commit only after the tests pass.

This approach reduces accidental partial edits and makes each development step
easier to review and recover.

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

The near-term roadmap is:

```text
Sprint 77
Risk Management Engine

Sprint 78+
Risk integration and operational controls

Sprint 79.5
Quality, warnings, and regression hardening

Sprint 80
Beta milestone

Later sprints
Live brokerage integration and production safeguards
```

The roadmap may be adjusted as testing reveals new safety or architectural
requirements.
