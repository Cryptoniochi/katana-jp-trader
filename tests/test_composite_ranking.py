"""複合最適化スコアランキングのテスト。"""

from datetime import time

import pytest

from app.backtest.composite_ranking import (
    CompositeOptimizationRanking,
    CompositeOptimizationRankingService,
)
from app.backtest.composite_score_models import (
    CompositeOptimizationScore,
    CompositeOptimizationScoreReport,
    CompositeScoreComponents,
    CompositeScoreWeights,
)
from app.backtest.optimization_models import (
    OrbOptimizationParameters,
)
from app.backtest.optimization_result_models import (
    OptimizationRunStatus,
    OrbOptimizationRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)


def metrics() -> BacktestPerformanceMetrics:
    """テスト用成績指標を作成する。"""

    return BacktestPerformanceMetrics(
        trade_count=1,
        winning_trade_count=1,
        losing_trade_count=0,
        flat_trade_count=0,
        gross_profit=1000.0,
        gross_loss=0.0,
        net_profit_loss=1000.0,
        win_rate=1.0,
        profit_factor=None,
        average_profit=1000.0,
        average_loss=None,
        expectancy=1000.0,
        maximum_consecutive_wins=1,
        maximum_consecutive_losses=0,
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def score(
    *,
    minute: int,
    value: float,
) -> CompositeOptimizationScore:
    """指定値の複合スコアを作成する。"""

    run = OrbOptimizationRunResult(
        parameter=OrbOptimizationParameters(
            stop_loss_rate=0.02,
            take_profit_rate=0.04,
            opening_range_end=time(9, minute),
        ),
        status=OptimizationRunStatus.COMPLETED,
        metrics=metrics(),
        equity_curve_report=None,
    )

    return CompositeOptimizationScore(
        run=run,
        score=value,
        components=CompositeScoreComponents(
            net_profit=value,
            profit_factor=value,
            win_rate=value,
            maximum_drawdown=value,
        ),
        weights=CompositeScoreWeights(),
    )


def test_service_ranks_scores_descending() -> None:
    """複合スコア降順に順位付けする。"""

    low = score(minute=10, value=0.2)
    high = score(minute=15, value=0.9)
    middle = score(minute=20, value=0.6)

    ranking = (
        CompositeOptimizationRankingService()
        .rank(
            CompositeOptimizationScoreReport(
                scores=(low, high, middle)
            )
        )
    )

    assert [
        item.score
        for item in ranking.items
    ] == [0.9, 0.6, 0.2]
    assert [
        item.rank
        for item in ranking.items
    ] == [1, 2, 3]
    assert ranking.best is not None
    assert ranking.best.parameter_id == (
        high.parameter_id
    )


def test_service_uses_parameter_id_for_ties() -> None:
    """同点時はパラメータID昇順で安定化する。"""

    first = score(minute=10, value=0.5)
    second = score(minute=15, value=0.5)

    ranking = (
        CompositeOptimizationRankingService()
        .rank(
            CompositeOptimizationScoreReport(
                scores=(second, first)
            )
        )
    )

    assert [
        item.parameter_id
        for item in ranking.items
    ] == sorted(
        [
            first.parameter_id,
            second.parameter_id,
        ]
    )


def test_service_supports_top_n() -> None:
    """上位N件だけ返す。"""

    ranking = (
        CompositeOptimizationRankingService()
        .rank(
            CompositeOptimizationScoreReport(
                scores=(
                    score(minute=10, value=0.3),
                    score(minute=15, value=0.8),
                    score(minute=20, value=0.5),
                )
            ),
            top_n=2,
        )
    )

    assert ranking.item_count == 2
    assert [
        item.rank
        for item in ranking.items
    ] == [1, 2]


def test_service_accepts_empty_report() -> None:
    """空レポートでは空ランキングを返す。"""

    ranking = (
        CompositeOptimizationRankingService()
        .rank(
            CompositeOptimizationScoreReport(
                scores=()
            )
        )
    )

    assert ranking.items == ()
    assert ranking.best is None


def test_service_rejects_invalid_top_n() -> None:
    """0以下のTop Nを拒否する。"""

    with pytest.raises(ValueError, match="top_n"):
        CompositeOptimizationRankingService().rank(
            CompositeOptimizationScoreReport(
                scores=()
            ),
            top_n=0,
        )


def test_ranking_get_returns_item() -> None:
    """パラメータIDから順位結果を取得する。"""

    value = score(minute=15, value=0.7)

    ranking = (
        CompositeOptimizationRankingService()
        .rank(
            CompositeOptimizationScoreReport(
                scores=(value,)
            )
        )
    )

    assert ranking.get(
        value.parameter_id
    ).rank == 1


def test_ranking_get_rejects_unknown_id() -> None:
    """存在しないパラメータIDを拒否する。"""

    ranking = CompositeOptimizationRanking(
        items=()
    )

    with pytest.raises(KeyError, match="存在しません"):
        ranking.get("missing")
