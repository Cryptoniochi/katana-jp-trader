"""複合最適化スコアのテスト。"""

from datetime import datetime, time, timezone

import pytest

from app.backtest.composite_score_models import (
    CompositeScoreWeights,
)
from app.backtest.composite_score_service import (
    CompositeOptimizationScoreService,
)
from app.backtest.optimization_models import (
    OrbOptimizationParameters,
)
from app.backtest.optimization_result_models import (
    OptimizationRunStatus,
    OrbOptimizationResult,
    OrbOptimizationRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.trading.equity_curve_models import (
    EquityCurvePoint,
    EquityCurveReport,
)


NOW = datetime(
    2026,
    7,
    1,
    tzinfo=timezone.utc,
)


def metrics(
    *,
    net_profit: float,
    profit_factor: float | None,
    win_rate: float | None,
) -> BacktestPerformanceMetrics:
    """テスト用成績指標を作成する。"""

    return BacktestPerformanceMetrics(
        trade_count=1,
        winning_trade_count=int(net_profit > 0),
        losing_trade_count=int(net_profit < 0),
        flat_trade_count=int(net_profit == 0),
        gross_profit=max(0.0, net_profit),
        gross_loss=max(0.0, -net_profit),
        net_profit_loss=net_profit,
        win_rate=win_rate,
        profit_factor=profit_factor,
        average_profit=None,
        average_loss=None,
        expectancy=net_profit,
        maximum_consecutive_wins=0,
        maximum_consecutive_losses=0,
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def equity(
    *,
    drawdown: float,
) -> EquityCurveReport:
    """テスト用資産曲線を作成する。"""

    point = EquityCurvePoint(
        generated_at=NOW,
        equity=1_000_000.0,
        cash_balance=1_000_000.0,
        market_value=0.0,
        realized_profit_loss=0.0,
        unrealized_profit_loss=0.0,
        period_return=None,
        cumulative_return=0.0,
    )

    return EquityCurveReport(
        points=(point,),
        initial_equity=1_000_000.0,
        final_equity=1_000_000.0,
        absolute_profit_loss=0.0,
        total_return=0.0,
        maximum_drawdown=drawdown,
        maximum_drawdown_amount=(
            drawdown * 1_000_000.0
        ),
        winning_period_count=0,
        losing_period_count=0,
        flat_period_count=0,
    )


def run(
    *,
    minute: int,
    net_profit: float,
    profit_factor: float | None,
    win_rate: float | None,
    drawdown: float | None,
) -> OrbOptimizationRunResult:
    """正常完了した試行を作成する。"""

    return OrbOptimizationRunResult(
        parameter=OrbOptimizationParameters(
            stop_loss_rate=0.02,
            take_profit_rate=0.04,
            opening_range_end=time(9, minute),
        ),
        status=OptimizationRunStatus.COMPLETED,
        metrics=metrics(
            net_profit=net_profit,
            profit_factor=profit_factor,
            win_rate=win_rate,
        ),
        equity_curve_report=(
            None
            if drawdown is None
            else equity(drawdown=drawdown)
        ),
    )


def test_service_normalizes_and_scores_runs() -> None:
    """各指標を正規化して重み付けする。"""

    first = run(
        minute=10,
        net_profit=100.0,
        profit_factor=1.0,
        win_rate=0.4,
        drawdown=0.20,
    )
    second = run(
        minute=15,
        net_profit=300.0,
        profit_factor=2.0,
        win_rate=0.6,
        drawdown=0.10,
    )

    report = (
        CompositeOptimizationScoreService()
        .create_report(
            OrbOptimizationResult(
                runs=(first, second)
            )
        )
    )

    first_score = report.get(
        first.parameter_id
    )
    second_score = report.get(
        second.parameter_id
    )

    assert first_score.score == pytest.approx(0.0)
    assert second_score.score == pytest.approx(1.0)
    assert second_score.components.net_profit == 1.0
    assert second_score.components.profit_factor == 1.0
    assert second_score.components.win_rate == 1.0
    assert second_score.components.maximum_drawdown == 1.0


def test_service_inverts_drawdown_score() -> None:
    """小さいドローダウンほど高得点にする。"""

    high_drawdown = run(
        minute=10,
        net_profit=100.0,
        profit_factor=1.0,
        win_rate=0.5,
        drawdown=0.30,
    )
    low_drawdown = run(
        minute=15,
        net_profit=100.0,
        profit_factor=1.0,
        win_rate=0.5,
        drawdown=0.05,
    )

    report = (
        CompositeOptimizationScoreService()
        .create_report(
            OrbOptimizationResult(
                runs=(
                    high_drawdown,
                    low_drawdown,
                )
            ),
            weights=CompositeScoreWeights(
                net_profit=0.0,
                profit_factor=0.0,
                win_rate=0.0,
                maximum_drawdown=1.0,
            ),
        )
    )

    assert report.get(
        low_drawdown.parameter_id
    ).score == pytest.approx(1.0)
    assert report.get(
        high_drawdown.parameter_id
    ).score == pytest.approx(0.0)


def test_service_normalizes_weights() -> None:
    """重み合計が1でなくても正規化する。"""

    value = run(
        minute=15,
        net_profit=100.0,
        profit_factor=1.5,
        win_rate=0.5,
        drawdown=0.1,
    )

    report = (
        CompositeOptimizationScoreService()
        .create_report(
            OrbOptimizationResult(
                runs=(value,)
            ),
            weights=CompositeScoreWeights(
                net_profit=4.0,
                profit_factor=3.0,
                win_rate=2.0,
                maximum_drawdown=1.0,
            ),
        )
    )

    score = report.scores[0]

    assert score.score == pytest.approx(1.0)
    assert 0.0 <= score.score <= 1.0
    assert score.weights.total == pytest.approx(1.0)
    assert score.weights.net_profit == pytest.approx(0.4)


def test_service_handles_missing_metrics() -> None:
    """欠損PF・勝率・資産曲線を最低評価として扱う。"""

    missing = run(
        minute=10,
        net_profit=100.0,
        profit_factor=None,
        win_rate=None,
        drawdown=None,
    )
    complete = run(
        minute=15,
        net_profit=100.0,
        profit_factor=2.0,
        win_rate=0.7,
        drawdown=0.1,
    )

    report = (
        CompositeOptimizationScoreService()
        .create_report(
            OrbOptimizationResult(
                runs=(missing, complete)
            )
        )
    )

    missing_score = report.get(
        missing.parameter_id
    )
    complete_score = report.get(
        complete.parameter_id
    )

    assert (
        missing_score.components.profit_factor
        == pytest.approx(0.0)
    )
    assert (
        missing_score.components.win_rate
        == pytest.approx(0.0)
    )
    assert (
        missing_score.components.maximum_drawdown
        == pytest.approx(0.0)
    )
    assert complete_score.score > missing_score.score
    assert 0.0 <= complete_score.score <= 1.0


def test_service_returns_empty_report() -> None:
    """正常完了試行がなければ空レポートを返す。"""

    report = (
        CompositeOptimizationScoreService()
        .create_report(
            OrbOptimizationResult(runs=())
        )
    )

    assert report.scores == ()
    assert report.score_count == 0


def test_weights_reject_all_zero() -> None:
    """重み合計0を拒否する。"""

    with pytest.raises(ValueError, match="重み合計"):
        CompositeScoreWeights(
            net_profit=0.0,
            profit_factor=0.0,
            win_rate=0.0,
            maximum_drawdown=0.0,
        )


def test_weights_reject_negative_value() -> None:
    """負の重みを拒否する。"""

    with pytest.raises(ValueError, match="0以上"):
        CompositeScoreWeights(
            net_profit=-1.0,
        )
