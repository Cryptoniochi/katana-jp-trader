"""Watch List ORBパラメータ最適化のテスト。"""

import csv
from datetime import datetime, time
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.watchlist_optimizer import (
    WatchlistOrbOptimizationWriter,
    WatchlistOrbOptimizer,
)
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice


def create_price(
    code: str,
    time_text: str,
    *,
    high: float,
    low: float,
    close: float,
) -> StockPrice:
    """最適化テスト用の5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"2026-07-13 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=200_000,
    )


def create_symbol_prices(
    code: str,
    final_close: float,
) -> list[StockPrice]:
    """ORB取引が発生する株価一覧を作る。"""

    return [
        create_price(
            code,
            "09:00",
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            code,
            "09:05",
            high=1008,
            low=998,
            close=1005,
        ),
        create_price(
            code,
            "09:10",
            high=1010,
            low=1000,
            close=1007,
        ),
        create_price(
            code,
            "09:15",
            high=1012,
            low=1005,
            close=1010,
        ),
        create_price(
            code,
            "09:20",
            high=1020,
            low=1008,
            close=1015,
        ),
        create_price(
            code,
            "14:50",
            high=max(1035, final_close),
            low=min(990, final_close),
            close=final_close,
        ),
    ]


def create_optimizer(
    tmp_path: Path,
) -> tuple[
    WatchlistOrbOptimizer,
    MarketBarRepository,
]:
    """テスト用OptimizerとRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = MarketBarRepository(database_path)

    optimizer = WatchlistOrbOptimizer(
        repository=repository,
        engine=BacktestEngine(),
        quantity=100,
        commission=0.0,
        slippage_rate=0.0,
    )

    return optimizer, repository


def run_optimizer(
    optimizer: WatchlistOrbOptimizer,
):
    """固定条件でOptimizerを実行する。"""

    return optimizer.run(
        codes=["7203", "8306"],
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
        opening_range_ends=[
            time(9, 10),
            time(9, 15),
        ],
        stop_loss_rates=[
            0.01,
            0.02,
        ],
        take_profit_rates=[
            0.01,
            0.02,
        ],
    )


def test_optimizer_runs_all_combinations(
    tmp_path: Path,
) -> None:
    """全パラメータの組み合わせを検証する。"""

    optimizer, repository = create_optimizer(tmp_path)

    repository.save_all(
        prices=[
            *create_symbol_prices(
                "7203",
                final_close=1030,
            ),
            *create_symbol_prices(
                "8306",
                final_close=1000,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = run_optimizer(optimizer)

    assert report.combination_count == 8
    assert len(report.results) == 8
    assert report.best_result is not None


def test_optimizer_aggregates_watchlist_trades(
    tmp_path: Path,
) -> None:
    """Watch List全銘柄の取引を合算する。"""

    optimizer, repository = create_optimizer(tmp_path)

    repository.save_all(
        prices=[
            *create_symbol_prices(
                "7203",
                final_close=1030,
            ),
            *create_symbol_prices(
                "8306",
                final_close=1000,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = run_optimizer(optimizer)

    assert all(item.symbol_count == 2 for item in report.results)

    assert all(item.data_symbol_count == 2 for item in report.results)


def test_optimizer_accepts_missing_symbol_data(
    tmp_path: Path,
) -> None:
    """一部銘柄のデータがなくても最適化を継続する。"""

    optimizer, repository = create_optimizer(tmp_path)

    repository.save_all(
        prices=create_symbol_prices(
            "7203",
            final_close=1030,
        ),
        interval_minutes=5,
        data_source="test",
    )

    report = run_optimizer(optimizer)

    assert all(item.symbol_count == 2 for item in report.results)

    assert all(item.data_symbol_count == 1 for item in report.results)


def test_optimizer_sorts_by_total_profit(
    tmp_path: Path,
) -> None:
    """総損益が高い結果を上位へ並べる。"""

    optimizer, repository = create_optimizer(tmp_path)

    repository.save_all(
        prices=[
            *create_symbol_prices(
                "7203",
                final_close=1030,
            ),
            *create_symbol_prices(
                "8306",
                final_close=1000,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = run_optimizer(optimizer)

    total_profits = [item.result.total_profit for item in report.results]

    assert total_profits == sorted(
        total_profits,
        reverse=True,
    )


def test_writer_outputs_ranking_csv(
    tmp_path: Path,
) -> None:
    """最適化ランキングをCSVへ出力できる。"""

    optimizer, repository = create_optimizer(tmp_path)

    repository.save_all(
        prices=create_symbol_prices(
            "7203",
            final_close=1030,
        ),
        interval_minutes=5,
        data_source="test",
    )

    report = optimizer.run(
        codes=["7203"],
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
        opening_range_ends=[time(9, 15)],
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    file_path = tmp_path / "optimization.csv"

    output_path = WatchlistOrbOptimizationWriter().write_ranking(
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
    assert rows[0]["rank"] == "1"
    assert rows[0]["opening_range_end"] == "09:15"
    assert float(rows[0]["stop_loss_rate"]) == pytest.approx(0.01)
    assert float(rows[0]["take_profit_rate"]) == pytest.approx(0.02)


@pytest.mark.parametrize(
    (
        "opening_range_ends",
        "stop_loss_rates",
        "take_profit_rates",
        "message",
    ),
    [
        (
            [],
            [0.01],
            [0.02],
            "オープニングレンジ",
        ),
        (
            [time(9, 15)],
            [],
            [0.02],
            "損切り率",
        ),
        (
            [time(9, 15)],
            [0.01],
            [],
            "利確率",
        ),
        (
            [time(9, 15)],
            [0.0],
            [0.02],
            "損切り率",
        ),
        (
            [time(9, 15)],
            [0.01],
            [-0.02],
            "利確率",
        ),
    ],
)
def test_optimizer_rejects_invalid_candidates(
    tmp_path: Path,
    opening_range_ends: list[time],
    stop_loss_rates: list[float],
    take_profit_rates: list[float],
    message: str,
) -> None:
    """不正なパラメータ候補を拒否する。"""

    optimizer, _repository = create_optimizer(tmp_path)

    with pytest.raises(ValueError, match=message):
        optimizer.run(
            codes=["7203"],
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
            opening_range_ends=opening_range_ends,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )
