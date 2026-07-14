"""複数銘柄ORBバックテストのテスト。"""

import csv
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.multi_symbol import (
    MultiSymbolBacktestReportWriter,
    MultiSymbolOrbBacktestService,
)
from app.market.historical_csv_reader import HistoricalCsvReader
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def write_symbol_day(
    writer: csv.writer,
    code: str,
    date_text: str,
    *,
    breakout_close: float,
    final_close: float,
) -> None:
    """1銘柄・1営業日分のテスト用5分足を書く。"""

    opening_price = 1000.0

    writer.writerows(
        [
            [
                code,
                f"{date_text}T09:00:00",
                opening_price,
                1005.0,
                995.0,
                1000.0,
                100_000,
            ],
            [
                code,
                f"{date_text}T09:15:00",
                1000.0,
                1010.0,
                998.0,
                1005.0,
                120_000,
            ],
            [
                code,
                f"{date_text}T09:20:00",
                1005.0,
                1020.0,
                1004.0,
                breakout_close,
                180_000,
            ],
            [
                code,
                f"{date_text}T14:50:00",
                breakout_close,
                max(
                    breakout_close,
                    final_close,
                )
                + 1.0,
                min(
                    breakout_close,
                    final_close,
                )
                - 1.0,
                final_close,
                300_000,
            ],
        ]
    )


def write_multi_symbol_csv(
    file_path: Path,
) -> None:
    """複数銘柄のテスト用CSVを作成する。"""

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

        write_symbol_day(
            writer,
            "7203",
            "2026-07-13",
            breakout_close=1010.0,
            final_close=1020.0,
        )
        write_symbol_day(
            writer,
            "9984",
            "2026-07-13",
            breakout_close=1010.0,
            final_close=1000.0,
        )


def create_service() -> MultiSymbolOrbBacktestService:
    """テスト用サービスを作成する。"""

    return MultiSymbolOrbBacktestService(
        historical_reader=HistoricalCsvReader(),
        strategy=OpeningRangeBreakoutStrategy(
            quantity=100,
            stop_loss_rate=0.05,
            take_profit_rate=0.05,
            commission=0.0,
            slippage_rate=0.0,
        ),
        engine=BacktestEngine(),
    )


def test_service_calculates_each_symbol(
    tmp_path: Path,
) -> None:
    """複数銘柄を個別に集計できる。"""

    write_multi_symbol_csv(tmp_path / "prices.csv")

    report = create_service().run(tmp_path)

    assert report.symbol_count == 2
    assert report.traded_symbol_count == 2
    assert report.total_result.trade_count == 2

    results_by_code = {
        symbol_result.code: symbol_result.result
        for symbol_result in report.symbol_results
    }

    assert results_by_code["7203"].trade_count == 1
    assert results_by_code["7203"].total_profit == pytest.approx(1000.0)

    assert results_by_code["9984"].trade_count == 1
    assert results_by_code["9984"].total_profit == pytest.approx(-1000.0)

    assert report.total_result.total_profit == pytest.approx(0.0)


def test_service_ranks_profitable_symbol_first(
    tmp_path: Path,
) -> None:
    """総損益が高い銘柄を先頭に並べる。"""

    write_multi_symbol_csv(tmp_path / "prices.csv")

    report = create_service().run(tmp_path)

    assert report.symbol_results[0].code == "7203"
    assert report.symbol_results[1].code == "9984"


def test_report_writer_outputs_symbol_results(
    tmp_path: Path,
) -> None:
    """銘柄別成績をCSVへ出力できる。"""

    write_multi_symbol_csv(tmp_path / "prices.csv")

    report = create_service().run(tmp_path)
    report_path = tmp_path / "symbols.csv"

    output_path = MultiSymbolBacktestReportWriter().write_symbol_results(
        report=report,
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

    assert len(rows) == 2
    assert rows[0]["rank"] == "1"
    assert rows[0]["code"] == "7203"
    assert rows[1]["code"] == "9984"


def test_service_rejects_empty_prices() -> None:
    """株価データが空なら拒否する。"""

    with pytest.raises(
        ValueError,
        match="株価データ",
    ):
        create_service().run_prices([])
