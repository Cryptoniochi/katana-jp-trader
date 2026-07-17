"""OptimizationReportWriterのテスト。"""

import csv
import json
from datetime import time
from pathlib import Path

from app.backtest.composite_ranking import (
    CompositeOptimizationRankingService,
)
from app.backtest.composite_score_models import (
    CompositeScoreWeights,
)
from app.backtest.composite_score_service import (
    CompositeOptimizationScoreService,
)
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
    assert paths.best_parameters_json is None
    assert len(rows) == 2
    assert "composite_score" in rows[0]
    assert payload["run_count"] == 2
    assert payload["completed_count"] == 2
    assert payload["ranking_method"] == "net_profit"
    assert payload["best_parameter"] == (
        ranking[0].run.parameter_id
    )
    assert payload["best_score"] == 2000.0
    assert payload["ranking"][0]["rank"] == 1


def test_writer_outputs_composite_scores(
    tmp_path: Path,
) -> None:
    result = OrbOptimizationResult(
        runs=(
            create_run(10, -1000.0),
            create_run(15, 2000.0),
        )
    )
    weights = CompositeScoreWeights(
        net_profit=4.0,
        profit_factor=3.0,
        win_rate=2.0,
        maximum_drawdown=1.0,
    )
    score_report = (
        CompositeOptimizationScoreService()
        .create_report(
            result,
            weights=weights,
        )
    )
    ranking = (
        CompositeOptimizationRankingService()
        .rank(score_report)
    )

    paths = OptimizationReportWriter().write(
        output_directory=tmp_path,
        result=result,
        ranking=ranking,
        ranking_method="composite",
        composite_score_report=score_report,
        weights=weights,
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
    by_parameter_id = {
        row["parameter_id"]: row
        for row in rows
    }
    best = ranking.best

    assert best is not None
    best_row = by_parameter_id[best.parameter_id]

    assert best_row["rank"] == "1"
    assert float(
        best_row["composite_score"]
    ) == best.score
    assert best_row["net_profit_score"] != ""
    assert best_row["profit_factor_score"] != ""
    assert best_row["win_rate_score"] != ""
    assert best_row["drawdown_score"] != ""

    assert payload["ranking_method"] == "composite"
    assert payload["best_parameter"] == best.parameter_id
    assert payload["best_score"] == best.score
    assert payload["weights"] == {
        "maximum_drawdown": 0.1,
        "net_profit": 0.4,
        "profit_factor": 0.3,
        "win_rate": 0.2,
    }
    assert payload["ranking"][0]["score"] == best.score
    assert (
        payload["runs"][0]["composite_score"]
        is not None
    )


def test_writer_saves_best_parameters_json(
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
        save_best=True,
    )

    assert paths.best_parameters_json is not None
    payload = json.loads(
        paths.best_parameters_json.read_text(
            encoding="utf-8"
        )
    )

    assert payload == {
        "opening_range_end": "09:15",
        "parameter_id": ranking[0].run.parameter_id,
        "ranking_method": "net_profit",
        "score": 2000.0,
        "stop_loss_rate": 0.02,
        "take_profit_rate": 0.04,
        "weights": None,
    }
