"""履歴CSVによるORBバックテストのテスト。"""

import csv
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.historical_service import (
    HistoricalOrbBacktestService,
)
from app.market.historical_csv_reader import HistoricalCsvReader
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def test_historical_orb_backtest_runs_multiple_days(
    tmp_path: Path,
) -> None:
    """複数日分のCSVからORB取引を生成・集計できる。"""

    csv_path = tmp_path / "prices.csv"

    rows = [
        ["7203", "2026-07-13T09:00:00", 3500, 3510, 3495, 3505, 100000],
        ["7203", "2026-07-13T09:15:00", 3515, 3525, 3510, 3520, 130000],
        ["7203", "2026-07-13T09:25:00", 3518, 3535, 3518, 3530, 180000],
        ["7203", "2026-07-13T15:30:00", 3540, 3550, 3535, 3545, 300000],
        ["7203", "2026-07-14T09:00:00", 3540, 3550, 3535, 3545, 100000],
        ["7203", "2026-07-14T09:15:00", 3555, 3565, 3550, 3560, 130000],
        ["7203", "2026-07-14T09:20:00", 3560, 3575, 3555, 3570, 200000],
        ["7203", "2026-07-14T15:30:00", 3520, 3530, 3500, 3510, 320000],
    ]

    with csv_path.open(
        mode="w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "code",
                "traded_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )
        writer.writerows(rows)

    service = HistoricalOrbBacktestService(
        historical_reader=HistoricalCsvReader(),
        strategy=OpeningRangeBreakoutStrategy(
            quantity=100,
        ),
        engine=BacktestEngine(),
    )

    result = service.run(tmp_path)

    assert result.trade_count == 2
    assert result.win_count == 1
    assert result.loss_count == 1
    assert result.breakeven_count == 0
    assert result.win_rate == pytest.approx(50.0)

    assert result.gross_profit == pytest.approx(1500.0)
    assert result.gross_loss == pytest.approx(-6000.0)
    assert result.total_profit == pytest.approx(-4500.0)
    assert result.max_drawdown == pytest.approx(6000.0)
