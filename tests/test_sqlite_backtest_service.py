"""SQLite ORBバックテストサービスのテスト。"""

from datetime import datetime
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.sqlite_service import (
    SqliteOrbBacktestService,
)
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def create_price(
    time_text: str,
    *,
    high: float,
    low: float,
    close: float,
    volume: int = 100_000,
) -> StockPrice:
    """テスト用の7203の5分足を作成する。"""

    return StockPrice(
        code="7203",
        datetime=datetime.strptime(
            f"2026-07-13 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def create_service(
    tmp_path: Path,
) -> tuple[
    SqliteOrbBacktestService,
    MarketBarRepository,
]:
    """テスト用サービスとRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = MarketBarRepository(database_path)

    strategy = OpeningRangeBreakoutStrategy(
        quantity=100,
        stop_loss_rate=0.05,
        take_profit_rate=0.05,
        commission=0.0,
        slippage_rate=0.0,
    )

    service = SqliteOrbBacktestService(
        repository=repository,
        strategy=strategy,
        engine=BacktestEngine(),
    )

    return service, repository


def test_service_runs_orb_from_sqlite(
    tmp_path: Path,
) -> None:
    """SQLiteの5分足からORB取引を生成できる。"""

    service, repository = create_service(tmp_path)

    prices = [
        create_price(
            "09:00",
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            "09:05",
            high=1008,
            low=998,
            close=1005,
        ),
        create_price(
            "09:10",
            high=1010,
            low=1000,
            close=1007,
        ),
        create_price(
            "09:15",
            high=1012,
            low=1005,
            close=1010,
        ),
        create_price(
            "09:20",
            high=1020,
            low=1008,
            close=1015,
        ),
        create_price(
            "14:50",
            high=1030,
            low=1010,
            close=1025,
        ),
    ]

    repository.save_all(
        prices=prices,
        interval_minutes=5,
        data_source="test",
    )

    report = service.run(
        code="7203",
        interval_minutes=5,
        start_at=datetime(
            2026,
            7,
            13,
            0,
            0,
        ),
        end_at=datetime(
            2026,
            7,
            13,
            23,
            59,
            59,
        ),
    )

    assert report.code == "7203"
    assert report.interval_minutes == 5
    assert report.source_bar_count == 6

    assert len(report.trades) == 1
    assert report.result.trade_count == 1
    assert report.result.win_count == 1
    assert report.result.total_profit == pytest.approx(1000.0)


def test_service_returns_zero_trades_without_breakout(
    tmp_path: Path,
) -> None:
    """ブレイクがなければ取引0件として集計する。"""

    service, repository = create_service(tmp_path)

    repository.save_all(
        prices=[
            create_price(
                "09:00",
                high=1010,
                low=995,
                close=1000,
            ),
            create_price(
                "09:15",
                high=1020,
                low=1000,
                close=1010,
            ),
            create_price(
                "09:20",
                high=1020,
                low=1000,
                close=1005,
            ),
            create_price(
                "14:50",
                high=1015,
                low=995,
                close=1000,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = service.run(
        code="7203",
        interval_minutes=5,
        start_at=datetime(
            2026,
            7,
            13,
        ),
        end_at=datetime(
            2026,
            7,
            13,
            23,
            59,
            59,
        ),
    )

    assert report.source_bar_count == 4
    assert report.trades == []
    assert report.result.trade_count == 0
    assert report.result.total_profit == 0


def test_service_rejects_missing_sqlite_data(
    tmp_path: Path,
) -> None:
    """指定条件の時間足がなければ拒否する。"""

    service, _repository = create_service(tmp_path)

    with pytest.raises(
        ValueError,
        match="保存されていません",
    ):
        service.run(
            code="7203",
            interval_minutes=5,
            start_at=datetime(
                2026,
                7,
                13,
            ),
            end_at=datetime(
                2026,
                7,
                13,
                23,
                59,
                59,
            ),
        )


def test_service_rejects_reversed_date_range(
    tmp_path: Path,
) -> None:
    """開始日時が終了日時より後なら拒否する。"""

    service, _repository = create_service(tmp_path)

    with pytest.raises(
        ValueError,
        match="開始日時",
    ):
        service.run(
            code="7203",
            interval_minutes=5,
            start_at=datetime(
                2026,
                7,
                14,
            ),
            end_at=datetime(
                2026,
                7,
                13,
            ),
        )
