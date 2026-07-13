"""CSVバックテストサービスのテスト。"""

import csv
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.service import CsvBacktestService
from app.market.csv_reader import CsvStockReader
from app.strategy.buy_open_sell_close import BuyOpenSellCloseStrategy


def test_csv_backtest_service_runs_backtest(
    tmp_path: Path,
) -> None:
    """CSVを読み込み、戦略とバックテストを実行できる。"""

    csv_path = tmp_path / "prices.csv"

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

        writer.writerow(
            [
                "7203",
                "2026-07-13T09:00:00",
                3500.0,
                3520.0,
                3490.0,
                3510.0,
                1000,
            ]
        )

        writer.writerow(
            [
                "7203",
                "2026-07-13T15:30:00",
                3510.0,
                3540.0,
                3500.0,
                3535.0,
                2000,
            ]
        )

    service = CsvBacktestService(
        csv_reader=CsvStockReader(),
        strategy=BuyOpenSellCloseStrategy(quantity=100),
        engine=BacktestEngine(),
    )

    result = service.run(csv_path)

    assert result.trade_count == 1
    assert result.win_count == 1
    assert result.loss_count == 0
    assert result.breakeven_count == 0
    assert result.win_rate == pytest.approx(100.0)
    assert result.total_profit == pytest.approx(3500.0)
    assert result.average_profit == pytest.approx(3500.0)
