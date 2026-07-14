"""ORB最適化エンジンのテスト。"""

import csv
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.orb_optimizer import OrbOptimizer
from app.market.historical_csv_reader import HistoricalCsvReader


def write_historical_csv(file_path: Path) -> None:
    """最適化テスト用の5分足CSVを作成する。"""

    rows = [
        [
            "7203",
            "2026-07-13T09:00:00",
            1000,
            1005,
            995,
            1000,
            100000,
        ],
        [
            "7203",
            "2026-07-13T09:15:00",
            1000,
            1010,
            998,
            1005,
            120000,
        ],
        [
            "7203",
            "2026-07-13T09:20:00",
            1005,
            1020,
            1004,
            1010,
            180000,
        ],
        [
            "7203",
            "2026-07-13T09:25:00",
            1010,
            1035,
            1008,
            1030,
            200000,
        ],
        [
            "7203",
            "2026-07-13T14:50:00",
            1030,
            1040,
            1020,
            1035,
            300000,
        ],
        [
            "7203",
            "2026-07-14T09:00:00",
            1000,
            1005,
            995,
            1000,
            100000,
        ],
        [
            "7203",
            "2026-07-14T09:15:00",
            1000,
            1010,
            998,
            1005,
            120000,
        ],
        [
            "7203",
            "2026-07-14T09:20:00",
            1005,
            1020,
            1004,
            1010,
            180000,
        ],
        [
            "7203",
            "2026-07-14T09:25:00",
            1010,
            1012,
            990,
            995,
            200000,
        ],
        [
            "7203",
            "2026-07-14T14:50:00",
            995,
            1000,
            985,
            990,
            300000,
        ],
    ]

    with file_path.open(
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


def test_optimizer_runs_all_parameter_combinations(
    tmp_path: Path,
) -> None:
    """損切り率と利確率の全組み合わせを検証する。"""

    write_historical_csv(tmp_path / "prices.csv")

    optimizer = OrbOptimizer(
        historical_reader=HistoricalCsvReader(),
        engine=BacktestEngine(),
        quantity=100,
        commission=0.0,
        slippage_rate=0.0,
    )

    results = optimizer.run(
        directory=tmp_path,
        stop_loss_rates=[0.01, 0.02],
        take_profit_rates=[0.01, 0.02, 0.03],
    )

    assert len(results) == 6

    combinations = {
        (
            result.stop_loss_rate,
            result.take_profit_rate,
        )
        for result in results
    }

    assert combinations == {
        (0.01, 0.01),
        (0.01, 0.02),
        (0.01, 0.03),
        (0.02, 0.01),
        (0.02, 0.02),
        (0.02, 0.03),
    }

    assert all(result.trade_count == 2 for result in results)


def test_optimizer_sorts_by_total_profit(
    tmp_path: Path,
) -> None:
    """総損益が高い結果を先頭へ並べる。"""

    write_historical_csv(tmp_path / "prices.csv")

    optimizer = OrbOptimizer(
        historical_reader=HistoricalCsvReader(),
        engine=BacktestEngine(),
        slippage_rate=0.0,
    )

    results = optimizer.run(
        directory=tmp_path,
        stop_loss_rates=[0.01, 0.02],
        take_profit_rates=[0.01, 0.02],
    )

    total_profits = [result.total_profit for result in results]

    assert total_profits == sorted(
        total_profits,
        reverse=True,
    )


def test_optimizer_writes_csv_report(
    tmp_path: Path,
) -> None:
    """最適化ランキングをCSVへ出力できる。"""

    write_historical_csv(tmp_path / "prices.csv")

    optimizer = OrbOptimizer(
        historical_reader=HistoricalCsvReader(),
        engine=BacktestEngine(),
        slippage_rate=0.0,
    )

    results = optimizer.run(
        directory=tmp_path,
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    report_path = tmp_path / "result.csv"

    output_path = optimizer.write_csv(
        results=results,
        file_path=report_path,
    )

    assert output_path == report_path
    assert report_path.exists()

    with report_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 1
    assert rows[0]["rank"] == "1"
    assert float(rows[0]["stop_loss_rate"]) == pytest.approx(0.01)
    assert float(rows[0]["take_profit_rate"]) == pytest.approx(0.02)


@pytest.mark.parametrize(
    ("stop_loss_rates", "take_profit_rates", "message"),
    [
        ([], [0.02], "損切り率"),
        ([0.01], [], "利確率"),
        ([0.0], [0.02], "損切り率"),
        ([0.01], [-0.02], "利確率"),
    ],
)
def test_optimizer_rejects_invalid_rate_candidates(
    tmp_path: Path,
    stop_loss_rates: list[float],
    take_profit_rates: list[float],
    message: str,
) -> None:
    """不正または空のパラメータ候補を拒否する。"""

    write_historical_csv(tmp_path / "prices.csv")

    optimizer = OrbOptimizer(
        historical_reader=HistoricalCsvReader(),
        engine=BacktestEngine(),
    )

    with pytest.raises(ValueError, match=message):
        optimizer.run(
            directory=tmp_path,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )
