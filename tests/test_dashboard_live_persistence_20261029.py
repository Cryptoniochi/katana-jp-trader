import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from app.dashboard.dashboard_strategy_service import DashboardStrategyService


def test_live_executions_survive_dashboard_restart_without_trade_signals(tmp_path: Path) -> None:
    db = tmp_path / "katana.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE trade_signals (
                id INTEGER PRIMARY KEY,
                signal_id TEXT,
                strategy_name TEXT,
                generated_at TEXT,
                action TEXT
            );
            CREATE TABLE trade_executions (
                id INTEGER PRIMARY KEY,
                execution_id TEXT,
                signal_id TEXT,
                code TEXT,
                side TEXT,
                quantity INTEGER,
                execution_price REAL,
                executed_at TEXT,
                commission REAL,
                slippage REAL
            );
            CREATE TABLE live_protective_stops (
                id INTEGER PRIMARY KEY,
                code TEXT,
                entry_execution_key TEXT,
                trading_date TEXT,
                quantity INTEGER,
                fill_price REAL,
                stop_price REAL,
                stop_loss_rate REAL,
                state TEXT,
                exit_execution_key TEXT,
                exit_order_id TEXT
            );
        """)
        c.executemany(
            """INSERT INTO trade_executions
               (execution_id, signal_id, code, side, quantity, execution_price,
                executed_at, commission, slippage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("buy2395", "pullback-v1-2395-buy-20261029T020000+0000", "2395", "buy", 100, 1525.5, "2026-10-29T02:02:24+00:00", 0.0, 0.0),
                ("buy9603", "orb-v2-9603-buy-20261029T021500+0000", "9603", "buy", 100, 1021.5, "2026-10-29T02:15:36+00:00", 0.0, 0.0),
                ("sell2395", "pullback-v1-2395-exit-20261029T033500+0000", "2395", "sell", 100, 1537.0, "2026-10-29T03:35:26+00:00", 0.0, 0.0),
            ],
        )
        c.execute(
            """INSERT INTO live_protective_stops
               (code, entry_execution_key, trading_date, quantity, fill_price,
                stop_price, stop_loss_rate, state, exit_execution_key, exit_order_id)
               VALUES ('9603', 'orb-v2-9603-buy-20261029T021500+0000',
                       '2026-10-29', 100, 1021.5, 1011.285, 0.01,
                       'active', NULL, NULL)"""
        )
        c.commit()

    service = DashboardStrategyService(
        db,
        now_provider=lambda: datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc),
    )
    payload = service.create_payload(trading_date=date(2026, 10, 29))
    rows = {row.strategy_name: row for row in payload.strategies}

    assert sum(row.execution_count for row in payload.strategies) == 3
    assert sum(row.signal_count for row in payload.strategies) == 3
    assert rows["Pullback"].completed_trade_count == 1
    assert rows["Pullback"].net_profit_loss == 1150.0
    assert len(payload.recent_trades) == 3
    assert len(payload.recent_completed_trades) == 1
    assert payload.open_positions == ({
        "code": "9603",
        "side": "BUY",
        "quantity": 100,
        "average_cost": 1021.5,
        "market_price": None,
        "unrealized_profit_loss": None,
        "source": "live_protective_stops",
    },)
