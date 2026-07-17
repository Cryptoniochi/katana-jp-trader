"""WalkForwardReportWriterのテスト。"""

from __future__ import annotations

import csv
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)
from app.backtest.optimization_runner import (
    OrbOptimizationExecutionOutput,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.walk_forward_analyzer import (
    WalkForwardAnalyzer,
)
from app.backtest.walk_forward_report_writer import (
    WalkForwardReportWriter,
)
from app.backtest.walk_forward_runner import (
    WalkForwardRunner,
)
from app.backtest.walk_forward_window_service import (
    WalkForwardWindowService,
)


JST = ZoneInfo("Asia/Tokyo")


def create_series(
    trading_day_count: int = 8,
) -> HistoricalBarSeries:
    """指定日数・各日1本の系列を作成する。"""

    start = datetime(
        2026,
        7,
        1,
        9,
        0,
        tzinfo=JST,
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=tuple(
            HistoricalBar(
                code="7203",
                timeframe=MarketTimeframe.MINUTE_5,
                opened_at=start + timedelta(days=index),
                open_price=1000.0 + index,
                high_price=1010.0 + index,
                low_price=990.0 + index,
                close_price=1005.0 + index,
                volume=1000.0,
            )
            for index in range(trading_day_count)
        ),
    )


def metrics(
    profit: float,
) -> BacktestPerformanceMetrics:
    """テスト用成績指標を作成する。"""

    winner = profit > 0
    loser = profit < 0

    return BacktestPerformanceMetrics(
        trade_count=1,
        winning_trade_count=int(winner),
        losing_trade_count=int(loser),
        flat_trade_count=int(profit == 0),
        gross_profit=max(0.0, profit),
        gross_loss=max(0.0, -profit),
        net_profit_loss=profit,
        win_rate=1.0 if winner else 0.0,
        profit_factor=None if not loser else 0.0,
        average_profit=profit if winner else None,
        average_loss=-profit if loser else None,
        expectancy=profit,
        maximum_consecutive_wins=int(winner),
        maximum_consecutive_losses=int(loser),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def create_result():
    """2ウィンドウのWalk-Forward結果を作成する。"""

    first = OrbOptimizationParameters(
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
        opening_range_end=time(9, 10),
    )
    second = OrbOptimizationParameters(
        stop_loss_rate=0.02,
        take_profit_rate=0.04,
        opening_range_end=time(9, 15),
    )
    plan = WalkForwardWindowService().create_plan(
        create_series(),
        training_days=4,
        validation_days=2,
        step_days=2,
    )
    validation_count = 0

    def training_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        return OrbOptimizationExecutionOutput(
            metrics=metrics(
                100.0 if parameter == first else 300.0
            ),
            equity_curve_report=None,
        )

    def validation_executor(
        _series: HistoricalBarSeries,
        _parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        nonlocal validation_count
        validation_count += 1

        return OrbOptimizationExecutionOutput(
            metrics=metrics(
                50.0 if validation_count == 1 else -25.0
            ),
            equity_curve_report=None,
        )

    return WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=validation_executor,
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
    )


def test_writer_creates_three_report_files(
    tmp_path: Path,
) -> None:
    """3種類のレポートを作成する。"""

    result = create_result()
    summary = WalkForwardAnalyzer().create_summary(result)

    paths = WalkForwardReportWriter().write(
        output_directory=tmp_path / "walk-forward",
        result=result,
        summary=summary,
    )

    assert paths.summary_csv.exists()
    assert paths.windows_csv.exists()
    assert paths.summary_json.exists()
    assert paths.output_directory == (
        tmp_path / "walk-forward"
    )


def test_summary_csv_contains_oos_metrics(
    tmp_path: Path,
) -> None:
    """サマリーCSVへOOS集計値を保存する。"""

    result = create_result()
    summary = WalkForwardAnalyzer().create_summary(result)
    paths = WalkForwardReportWriter().write(
        output_directory=tmp_path,
        result=result,
        summary=summary,
    )

    with paths.summary_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = {
            row["metric"]: row["value"]
            for row in csv.DictReader(file)
        }

    assert rows["window_count"] == "2"
    assert rows["completed_window_count"] == "2"
    assert rows["failed_window_count"] == "0"
    assert (
        float(rows["validation_net_profit_loss"])
        == pytest.approx(25.0)
    )
    assert (
        float(rows["validation_profitable_window_rate"])
        == pytest.approx(0.5)
    )


def test_windows_csv_contains_window_details(
    tmp_path: Path,
) -> None:
    """ウィンドウ別CSVへ採用候補と検証成績を保存する。"""

    result = create_result()
    summary = WalkForwardAnalyzer().create_summary(result)
    paths = WalkForwardReportWriter().write(
        output_directory=tmp_path,
        result=result,
        summary=summary,
    )

    with paths.windows_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2
    assert rows[0]["status"] == "completed"
    assert rows[0]["ranking_method"] == "net_profit"
    assert rows[0]["selected_parameter_id"]
    assert rows[0]["opening_range_end"] == "09:15"
    assert rows[0]["validation_net_profit_loss"] == "50.0"
    assert rows[1]["validation_net_profit_loss"] == "-25.0"
    assert rows[0]["optimization_run_count"] == "2"
    assert rows[0]["optimization_completed_count"] == "2"
    assert rows[0]["optimization_failed_count"] == "0"


def test_summary_json_contains_plan_and_windows(
    tmp_path: Path,
) -> None:
    """JSONへプラン・集計・ウィンドウ詳細を保存する。"""

    result = create_result()
    summary = WalkForwardAnalyzer().create_summary(result)
    paths = WalkForwardReportWriter().write(
        output_directory=tmp_path,
        result=result,
        summary=summary,
    )
    payload = json.loads(
        paths.summary_json.read_text(
            encoding="utf-8"
        )
    )

    assert payload["plan"] == {
        "step_days": 2,
        "training_days": 4,
        "validation_days": 2,
        "window_count": 2,
    }
    assert payload["summary"]["window_count"] == 2
    assert (
        payload["summary"]["validation"]
        ["net_profit_loss"]
        == 25.0
    )
    assert len(payload["windows"]) == 2
    assert (
        payload["windows"][0]
        ["selected_parameter"]["opening_range_end"]
        == "09:15"
    )


def test_writer_supports_empty_result(
    tmp_path: Path,
) -> None:
    """空プランでもレポートを作成できる。"""

    first = OrbOptimizationParameters(
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
        opening_range_end=time(9, 10),
    )
    plan = WalkForwardWindowService().create_plan(
        create_series(3),
        training_days=3,
        validation_days=1,
    )
    output = OrbOptimizationExecutionOutput(
        metrics=metrics(0.0),
        equity_curve_report=None,
    )
    result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: output,
        validation_executor=lambda _series, _parameter: output,
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first,)
        ),
    )
    summary = WalkForwardAnalyzer().create_summary(result)

    paths = WalkForwardReportWriter().write(
        output_directory=tmp_path,
        result=result,
        summary=summary,
    )
    payload = json.loads(
        paths.summary_json.read_text(
            encoding="utf-8"
        )
    )

    assert payload["plan"]["window_count"] == 0
    assert payload["windows"] == []


def test_writer_rejects_inconsistent_summary(
    tmp_path: Path,
) -> None:
    """別結果由来のサマリーを拒否する。"""

    result = create_result()
    empty_plan = WalkForwardWindowService().create_plan(
        create_series(3),
        training_days=3,
        validation_days=1,
    )
    first = OrbOptimizationParameters(
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
        opening_range_end=time(9, 10),
    )
    output = OrbOptimizationExecutionOutput(
        metrics=metrics(0.0),
        equity_curve_report=None,
    )
    empty_result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: output,
        validation_executor=lambda _series, _parameter: output,
    ).run(
        empty_plan,
        grid=OrbOptimizationGrid(
            parameters=(first,)
        ),
    )
    inconsistent = WalkForwardAnalyzer().create_summary(
        empty_result
    )

    with pytest.raises(ValueError, match="件数"):
        WalkForwardReportWriter().write(
            output_directory=tmp_path,
            result=result,
            summary=inconsistent,
        )
