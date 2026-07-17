"""OptimizationReportWriterのテスト。"""

import csv
import json
from datetime import time
from pathlib import Path

from app.backtest.optimization_models import (
    OrbOptimizationParameters,
)
from app.backtest.optimization_ranking import (
    OptimizationRankingService,
    RankingMetric,
)
from app.backtest.optimization_report_writer import (
    OptimizationReportWriter,
)
from app.backtest.optimization_result_models import (
    OptimizationRunStatus,
    OrbOptimizationResult,
    OrbOptimizationRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)


def create_metrics(
    profit: float,
) -> BacktestPerformanceMetrics:
    winner = profit > 0
    loser = profit < 0
    flat = profit == 0

    return BacktestPerformanceMetrics(
        trade_count=1,
        winning_trade_count=int(winner),
        losing_trade_count=int(loser),
        flat_trade_count=int(flat),
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


def create_run(
    minute: int,
    profit: float,
) -> OrbOptimizationRunResult:
    return OrbOptimizationRunResult(
        parameter=OrbOptimizationParameters(
            stop_loss_rate=0.02,
            take_profit_rate=0.04,
            opening_range_end=time(9, minute),
        ),
        status=OptimizationRunStatus.COMPLETED,
        metrics=create_metrics(profit),
        equity_curve_report=None,
    )


def test_writer_creates_ranked_files(
    tmp_path: Path,
) -> None:
    result = OrbOptimizationResult(
        runs=(
            create_run(10, 1000.0),
            create_run(15, 2000.0),
        )
    )
    ranking = OptimizationRankingService().rank(
        result,
        metric=RankingMetric.NET_PROFIT,
    )

    paths = OptimizationReportWriter().write(
        output_directory=tmp_path,
        result=result,
        ranking=ranking,
    )

    with paths.optimization_csv.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    payload = json.loads(
        paths.optimization_json.read_text(
            encoding="utf-8"
        )
    )

    assert paths.optimization_csv.exists()
    assert paths.optimization_json.exists()
    assert len(rows) == 2
    assert payload["run_count"] == 2
    assert payload["completed_count"] == 2
    assert payload["ranking"][0]["rank"] == 1
