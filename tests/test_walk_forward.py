"""ORBウォークフォワード検証のテスト。"""

import csv
from datetime import datetime, time
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.walk_forward import (
    OrbWalkForwardService,
    WalkForwardReportWriter,
)
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice
from app.strategy.orb_profile import OrbStrategyProfile


def create_price(
    code: str,
    date_text: str,
    time_text: str,
    *,
    high: float,
    low: float,
    close: float,
    volume: int = 200_000,
) -> StockPrice:
    """テスト用5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def create_day_prices(
    code: str,
    date_text: str,
    *,
    final_close: float,
) -> list[StockPrice]:
    """1日分のORB候補データを作成する。"""

    return [
        create_price(
            code,
            date_text,
            "09:00",
            high=1005.0,
            low=995.0,
            close=1000.0,
        ),
        create_price(
            code,
            date_text,
            "09:05",
            high=1008.0,
            low=998.0,
            close=1005.0,
        ),
        create_price(
            code,
            date_text,
            "09:10",
            high=1010.0,
            low=1000.0,
            close=1007.0,
        ),
        create_price(
            code,
            date_text,
            "09:15",
            high=1012.0,
            low=1005.0,
            close=1010.0,
        ),
        create_price(
            code,
            date_text,
            "09:20",
            high=1020.0,
            low=1008.0,
            close=1015.0,
        ),
        create_price(
            code,
            date_text,
            "14:50",
            high=max(1035.0, final_close),
            low=min(995.0, final_close),
            close=final_close,
        ),
    ]


def create_service(
    tmp_path: Path,
) -> tuple[
    OrbWalkForwardService,
    MarketBarRepository,
]:
    """テスト用サービスとRepositoryを作る。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = MarketBarRepository(database_path)

    profile = OrbStrategyProfile(
        commission=0.0,
        slippage_rate=0.0,
        min_opening_range_volume=None,
        min_breakout_volume=None,
        breakout_volume_ratio=None,
        min_price=None,
        max_price=None,
        min_opening_range_turnover=None,
        min_breakout_turnover=None,
    )

    service = OrbWalkForwardService(
        repository=repository,
        engine=BacktestEngine(),
        profile=profile,
    )

    return service, repository


def test_walk_forward_creates_multiple_windows(
    tmp_path: Path,
) -> None:
    """複数の学習・検証ウィンドウを作成する。"""

    service, repository = create_service(tmp_path)

    prices: list[StockPrice] = []

    for day in range(1, 11):
        prices.extend(
            create_day_prices(
                "7203",
                f"2026-07-{day:02d}",
                final_close=1025.0,
            )
        )

    repository.save_all(
        prices=prices,
        interval_minutes=5,
        data_source="test",
    )

    report = service.run(
        codes=["7203"],
        interval_minutes=5,
        start_at=datetime(2026, 7, 1),
        end_at=datetime(
            2026,
            7,
            10,
            23,
            59,
            59,
        ),
        training_days=4,
        testing_days=2,
        step_days=2,
        opening_range_ends=[
            time(9, 10),
            time(9, 15),
        ],
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    assert report.window_count == 3
    assert len(report.windows) == 3


def test_walk_forward_uses_training_best_parameters(
    tmp_path: Path,
) -> None:
    """学習期間の最良条件を検証期間へ適用する。"""

    service, repository = create_service(tmp_path)

    prices: list[StockPrice] = []

    for day in range(1, 7):
        prices.extend(
            create_day_prices(
                "7203",
                f"2026-07-{day:02d}",
                final_close=1025.0,
            )
        )

    repository.save_all(
        prices=prices,
        interval_minutes=5,
        data_source="test",
    )

    report = service.run(
        codes=["7203"],
        interval_minutes=5,
        start_at=datetime(2026, 7, 1),
        end_at=datetime(
            2026,
            7,
            6,
            23,
            59,
            59,
        ),
        training_days=4,
        testing_days=2,
        step_days=2,
        opening_range_ends=[time(9, 15)],
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    assert report.window_count == 1

    result = report.windows[0]

    assert result.opening_range_end == time(9, 15)
    assert result.stop_loss_rate == pytest.approx(0.01)
    assert result.take_profit_rate == pytest.approx(0.02)
    assert result.training_result.trade_count > 0
    assert result.testing_result.trade_count > 0


def test_walk_forward_combines_testing_trades(
    tmp_path: Path,
) -> None:
    """全検証期間の取引を合算する。"""

    service, repository = create_service(tmp_path)

    prices: list[StockPrice] = []

    for day in range(1, 11):
        prices.extend(
            create_day_prices(
                "7203",
                f"2026-07-{day:02d}",
                final_close=1025.0,
            )
        )

    repository.save_all(
        prices=prices,
        interval_minutes=5,
        data_source="test",
    )

    report = service.run(
        codes=["7203"],
        interval_minutes=5,
        start_at=datetime(2026, 7, 1),
        end_at=datetime(
            2026,
            7,
            10,
            23,
            59,
            59,
        ),
        training_days=4,
        testing_days=2,
        step_days=2,
        opening_range_ends=[time(9, 15)],
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    expected_count = sum(item.testing_result.trade_count for item in report.windows)

    assert report.total_testing_result.trade_count == expected_count
    assert len(report.all_testing_trades) == (expected_count)


def test_writer_outputs_window_results(
    tmp_path: Path,
) -> None:
    """ウィンドウ別結果をCSVへ出力できる。"""

    service, repository = create_service(tmp_path)

    prices: list[StockPrice] = []

    for day in range(1, 7):
        prices.extend(
            create_day_prices(
                "7203",
                f"2026-07-{day:02d}",
                final_close=1025.0,
            )
        )

    repository.save_all(
        prices=prices,
        interval_minutes=5,
        data_source="test",
    )

    report = service.run(
        codes=["7203"],
        interval_minutes=5,
        start_at=datetime(2026, 7, 1),
        end_at=datetime(
            2026,
            7,
            6,
            23,
            59,
            59,
        ),
        training_days=4,
        testing_days=2,
        step_days=2,
        opening_range_ends=[time(9, 15)],
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    file_path = tmp_path / "walk_forward.csv"

    output_path = WalkForwardReportWriter().write_windows(
        report=report,
        file_path=file_path,
    )

    assert output_path == file_path
    assert file_path.exists()

    with file_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 1
    assert rows[0]["window"] == "1"
    assert rows[0]["opening_range_end"] == "09:15"


@pytest.mark.parametrize(
    (
        "training_days",
        "testing_days",
        "step_days",
        "message",
    ),
    [
        (0, 2, 2, "学習日数"),
        (4, 0, 2, "検証日数"),
        (4, 2, 0, "移動日数"),
    ],
)
def test_walk_forward_rejects_invalid_days(
    tmp_path: Path,
    training_days: int,
    testing_days: int,
    step_days: int,
    message: str,
) -> None:
    """不正なウィンドウ日数を拒否する。"""

    service, _repository = create_service(tmp_path)

    with pytest.raises(ValueError, match=message):
        service.run(
            codes=["7203"],
            interval_minutes=5,
            start_at=datetime(2026, 7, 1),
            end_at=datetime(
                2026,
                7,
                10,
                23,
                59,
                59,
            ),
            training_days=training_days,
            testing_days=testing_days,
            step_days=step_days,
            opening_range_ends=[time(9, 15)],
            stop_loss_rates=[0.01],
            take_profit_rates=[0.02],
        )


def test_walk_forward_rejects_short_period(
    tmp_path: Path,
) -> None:
    """学習・検証期間を作れない短期間を拒否する。"""

    service, _repository = create_service(tmp_path)

    with pytest.raises(
        ValueError,
        match="ウィンドウ",
    ):
        service.run(
            codes=["7203"],
            interval_minutes=5,
            start_at=datetime(2026, 7, 1),
            end_at=datetime(
                2026,
                7,
                3,
                23,
                59,
                59,
            ),
            training_days=4,
            testing_days=2,
            step_days=2,
            opening_range_ends=[time(9, 15)],
            stop_loss_rates=[0.01],
            take_profit_rates=[0.02],
        )
