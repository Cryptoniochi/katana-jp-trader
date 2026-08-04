"""SQLite優先Dashboard Snapshot Readerのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.database import initialize_database
from app.dashboard.dashboard_snapshot_file import (
    DashboardSqliteSnapshotReader,
)
from app.trading.broker_adapter import BrokerPositionSide
from app.trading.portfolio_models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from app.trading.portfolio_repository import PortfolioRepository


NOW = datetime(
    2026,
    8,
    4,
    4,
    0,
    tzinfo=timezone.utc,
)


def test_reader_overlays_latest_sqlite_portfolio(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    snapshot_path = tmp_path / "dashboard.json"
    initialize_database(database_path)

    snapshot_path.write_text(
        '{"generated_at":"2026-08-04T03:00:00+00:00",'
        '"portfolio":null,"errors":[]}',
        encoding="utf-8",
    )

    PortfolioRepository(
        database_path,
        now_provider=lambda: NOW,
    ).save(
        PortfolioSnapshot(
            currency="JPY",
            cash_balance=750_000.0,
            buying_power=750_000.0,
            broker_market_value=260_000.0,
            broker_equity=1_010_000.0,
            positions=(
                PortfolioPositionSnapshot(
                    position_id="position-7203-long",
                    code="7203",
                    side=BrokerPositionSide.LONG,
                    quantity=100,
                    average_cost=2500.0,
                    market_price=2600.0,
                    realized_profit_loss=0.0,
                ),
            ),
            generated_at=NOW,
        )
    )

    payload = DashboardSqliteSnapshotReader(
        database_path=database_path,
        snapshot_path=snapshot_path,
        now_provider=lambda: NOW,
    ).create_snapshot()

    assert payload["portfolio"]["position_count"] == 1
    assert payload["portfolio"]["positions"][0]["code"] == "7203"
    assert (
        payload["portfolio"]["positions"][0]
        ["unrealized_profit_loss"]
        == 10_000.0
    )


def test_reader_returns_empty_portfolio_without_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    payload = DashboardSqliteSnapshotReader(
        database_path=database_path,
        snapshot_path=tmp_path / "missing.json",
        now_provider=lambda: NOW,
    ).create_snapshot()

    assert payload["portfolio"]["position_count"] == 0
    assert payload["portfolio"]["positions"] == []
