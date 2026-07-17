"""バックテスト指標とレポートWriterのテスト。"""

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.backtest.backtest_report_writer import (
    BacktestReportWriter,
)
from app.backtest.performance_metrics_service import (
    BacktestPerformanceMetricsService,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
    CompletedBacktestTrade,
)
from app.trading.equity_curve_models import (
    EquityCurvePoint,
    EquityCurveReport,
)


BASE_TIME = datetime(
    2026,
    7,
    1,
    0,
    20,
    tzinfo=timezone.utc,
)


def trade(
    *,
    sequence: int,
    profit: float,
) -> CompletedBacktestTrade:
    """指定損益になるテスト用トレードを作成する。"""

    entry_price = 1000.0
    quantity = 100
    exit_price = (
        entry_price + profit / quantity
    )

    return CompletedBacktestTrade(
        trade_id=f"trade-{sequence}",
        code="7203",
        quantity=quantity,
        entry_execution_id=f"buy-{sequence}",
        exit_execution_id=f"sell-{sequence}",
        entry_signal_id=f"signal-buy-{sequence}",
        exit_signal_id=f"signal-sell-{sequence}",
        entered_at=(
            BASE_TIME
            + timedelta(minutes=sequence * 10)
        ),
        exited_at=(
            BASE_TIME
            + timedelta(minutes=sequence * 10 + 5)
        ),
        entry_price=entry_price,
        exit_price=exit_price,
        entry_commission=0.0,
        exit_commission=0.0,
        entry_slippage=0.0,
        exit_slippage=0.0,
        exit_reason="take_profit",
    )


def equity_report() -> EquityCurveReport:
    """テスト用資産曲線を作成する。"""

    points = (
        EquityCurvePoint(
            generated_at=BASE_TIME,
            equity=1_000_000.0,
            cash_balance=900_000.0,
            market_value=100_000.0,
            realized_profit_loss=0.0,
            unrealized_profit_loss=0.0,
            period_return=None,
            cumulative_return=0.0,
        ),
        EquityCurvePoint(
            generated_at=BASE_TIME + timedelta(minutes=5),
            equity=1_001_500.0,
            cash_balance=1_001_500.0,
            market_value=0.0,
            realized_profit_loss=1_500.0,
            unrealized_profit_loss=0.0,
            period_return=0.0015,
            cumulative_return=0.0015,
        ),
    )

    return EquityCurveReport(
        points=points,
        initial_equity=1_000_000.0,
        final_equity=1_001_500.0,
        absolute_profit_loss=1_500.0,
        total_return=0.0015,
        maximum_drawdown=0.0,
        maximum_drawdown_amount=0.0,
        winning_period_count=1,
        losing_period_count=0,
        flat_period_count=0,
    )


def test_metrics_service_calculates_statistics() -> None:
    """主要指標と連勝・連敗を算出する。"""

    report = BacktestTradeReport(
        trades=(
            trade(sequence=1, profit=1000.0),
            trade(sequence=2, profit=2000.0),
            trade(sequence=3, profit=-500.0),
            trade(sequence=4, profit=-1000.0),
            trade(sequence=5, profit=0.0),
        ),
        unmatched_buy_quantity=100,
        unmatched_sell_quantity=0,
    )

    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(report)
    )

    assert metrics.trade_count == 5
    assert metrics.winning_trade_count == 2
    assert metrics.losing_trade_count == 2
    assert metrics.flat_trade_count == 1
    assert metrics.gross_profit == pytest.approx(3000.0)
    assert metrics.gross_loss == pytest.approx(1500.0)
    assert metrics.net_profit_loss == pytest.approx(1500.0)
    assert metrics.win_rate == pytest.approx(0.4)
    assert metrics.profit_factor == pytest.approx(2.0)
    assert metrics.average_profit == pytest.approx(1500.0)
    assert metrics.average_loss == pytest.approx(750.0)
    assert metrics.expectancy == pytest.approx(300.0)
    assert metrics.maximum_consecutive_wins == 2
    assert metrics.maximum_consecutive_losses == 2
    assert metrics.unmatched_buy_quantity == 100


def test_metrics_service_handles_empty_report() -> None:
    """トレードなしでは任意指標をNoneにする。"""

    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(
            BacktestTradeReport(
                trades=(),
                unmatched_buy_quantity=0,
                unmatched_sell_quantity=0,
            )
        )
    )

    assert metrics.trade_count == 0
    assert metrics.win_rate is None
    assert metrics.profit_factor is None
    assert metrics.average_profit is None
    assert metrics.average_loss is None
    assert metrics.expectancy is None


def test_writer_creates_all_report_files(
    tmp_path: Path,
) -> None:
    """CSV・JSONの4ファイルを生成する。"""

    trade_report = BacktestTradeReport(
        trades=(
            trade(sequence=1, profit=1500.0),
        ),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )
    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(trade_report)
    )

    paths = BacktestReportWriter().write(
        output_directory=tmp_path / "report",
        trade_report=trade_report,
        metrics=metrics,
        equity_curve_report=equity_report(),
    )

    assert paths.trades_csv.exists()
    assert paths.equity_curve_csv.exists()
    assert paths.metrics_csv.exists()
    assert paths.summary_json.exists()


def test_writer_outputs_trade_and_equity_rows(
    tmp_path: Path,
) -> None:
    """トレードと資産曲線の内容をCSVへ保存する。"""

    trade_report = BacktestTradeReport(
        trades=(
            trade(sequence=1, profit=1500.0),
        ),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )
    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(trade_report)
    )

    paths = BacktestReportWriter().write(
        output_directory=tmp_path,
        trade_report=trade_report,
        metrics=metrics,
        equity_curve_report=equity_report(),
    )

    with paths.trades_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        trade_rows = list(
            csv.DictReader(file)
        )

    with paths.equity_curve_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        equity_rows = list(
            csv.DictReader(file)
        )

    assert len(trade_rows) == 1
    assert trade_rows[0]["code"] == "7203"
    assert float(
        trade_rows[0]["net_profit_loss"]
    ) == pytest.approx(1500.0)
    assert trade_rows[0]["exit_reason"] == "take_profit"

    assert len(equity_rows) == 2
    assert float(
        equity_rows[-1]["equity"]
    ) == pytest.approx(1_001_500.0)


def test_writer_outputs_metrics_and_summary_json(
    tmp_path: Path,
) -> None:
    """指標CSVとJSONサマリーを保存する。"""

    trade_report = BacktestTradeReport(
        trades=(
            trade(sequence=1, profit=1500.0),
        ),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )
    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(trade_report)
    )

    paths = BacktestReportWriter().write(
        output_directory=tmp_path,
        trade_report=trade_report,
        metrics=metrics,
        equity_curve_report=equity_report(),
    )

    with paths.metrics_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = {
            row["metric"]: row["value"]
            for row in csv.DictReader(file)
        }

    summary = json.loads(
        paths.summary_json.read_text(
            encoding="utf-8"
        )
    )

    assert float(
        rows["net_profit_loss"]
    ) == pytest.approx(1500.0)
    assert float(
        rows["total_return"]
    ) == pytest.approx(0.0015)
    assert summary["metrics"]["trade_count"] == 1
    assert summary["equity_curve"]["final_equity"] == (
        pytest.approx(1_001_500.0)
    )


def test_writer_handles_missing_equity_report(
    tmp_path: Path,
) -> None:
    """資産曲線がなくてもヘッダー付きCSVを出力する。"""

    trade_report = BacktestTradeReport(
        trades=(),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )
    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(trade_report)
    )

    paths = BacktestReportWriter().write(
        output_directory=tmp_path,
        trade_report=trade_report,
        metrics=metrics,
        equity_curve_report=None,
    )

    with paths.equity_curve_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    summary = json.loads(
        paths.summary_json.read_text(
            encoding="utf-8"
        )
    )

    assert rows == []
    assert summary["equity_curve"] is None
