"""保存済み5分足でORBバックテストと最適化を実行するCLI。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioUpdateService,
)
from app.backtest.backtest_report_writer import (
    BacktestReportPaths,
    BacktestReportWriter,
)
from app.backtest.backtest_session import BacktestSession
from app.backtest.composite_ranking import (
    CompositeOptimizationRankingService,
)
from app.backtest.composite_score_models import (
    CompositeScoreWeights,
)
from app.backtest.composite_score_service import (
    CompositeOptimizationScoreService,
)
from app.backtest.event_driven_backtest_runner import (
    EventDrivenBacktestRunResult,
    EventDrivenBacktestRunner,
)
from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
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
from app.backtest.optimization_runner import (
    OrbOptimizationExecutionOutput,
    OrbOptimizationRunner,
)
from app.backtest.optimization_service import (
    OrbOptimizationGridService,
)
from app.backtest.orb_signal_strategy import (
    OrbSignalStrategy,
    OrbSignalStrategySettings,
)
from app.backtest.order_queue import BacktestOrderQueue
from app.backtest.order_queue_service import (
    BacktestOrderQueueService,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.performance_metrics_service import (
    BacktestPerformanceMetricsService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionService,
)
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.backtest.trade_report_models import (
    BacktestTradeReport,
)
from app.backtest.trade_report_service import (
    TradeReportService,
)
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
from app.trading.equity_curve_models import EquityCurveReport
from app.trading.equity_curve_service import EquityCurveService
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncService,
)
from app.trading.order_repository import OrderRepository
from app.trading.order_service import SignalOrderService
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.portfolio_repository import PortfolioRepository
from app.trading.portfolio_service import PortfolioService
from app.trading.position_repository import PositionRepository
from app.trading.position_service import PositionService
from app.trading.signal_repository import SignalRepository
from app.trading.trade_execution_repository import (
    TradeExecutionRepository,
)


JST = ZoneInfo("Asia/Tokyo")
COMPOSITE_RANKING = "composite"


@dataclass(slots=True)
class MutableClock:
    """バックテスト時刻を保持する。"""

    current: datetime

    def now(self) -> datetime:
        return self.current

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        self.current = value.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    """CLI引数Parserを作成する。"""

    parser = argparse.ArgumentParser(
        description="Project KATANA ORB backtest"
    )
    parser.add_argument("--code", required=True)
    parser.add_argument("--from", dest="start_date", required=True)
    parser.add_argument("--to", dest="end_date", required=True)
    parser.add_argument(
        "--database",
        type=Path,
        default=settings.database_path,
    )
    parser.add_argument(
        "--state-database",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=10_000_000.0,
    )
    parser.add_argument("--quantity", type=int, default=100)
    parser.add_argument(
        "--optimize",
        action="store_true",
    )
    parser.add_argument(
        "--save-best",
        action="store_true",
        help="最適化1位をbest_parameters.jsonへ保存します。",
    )
    parser.add_argument(
        "--apply-best",
        action="store_true",
        help=(
            "最適化1位のパラメータで追試バックテストを実行します。"
            "best_parameters.jsonも保存します。"
        ),
    )
    parser.add_argument(
        "--stop-loss-candidates",
        default="0.01,0.02,0.03",
    )
    parser.add_argument(
        "--take-profit-candidates",
        default="0.02,0.04,0.06",
    )
    parser.add_argument(
        "--opening-range-end-candidates",
        default="09:10,09:15,09:20",
    )
    parser.add_argument(
        "--ranking",
        choices=[
            metric.value
            for metric in RankingMetric
        ]
        + [COMPOSITE_RANKING],
        default=None,
        help=(
            "最適化ランキング方式。"
            "未指定時は--optimization-metricを使用します。"
        ),
    )
    parser.add_argument(
        "--optimization-metric",
        choices=[
            metric.value
            for metric in RankingMetric
        ],
        default=RankingMetric.NET_PROFIT.value,
        help=(
            "互換用の単一指標ランキング指定。"
            "新規利用では--rankingを推奨します。"
        ),
    )
    parser.add_argument(
        "--top-n",
        "--optimization-top-n",
        dest="optimization_top_n",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--weight-net-profit",
        type=float,
        default=0.4,
    )
    parser.add_argument(
        "--weight-profit-factor",
        type=float,
        default=0.3,
    )
    parser.add_argument(
        "--weight-win-rate",
        type=float,
        default=0.2,
    )
    parser.add_argument(
        "--weight-drawdown",
        type=float,
        default=0.1,
    )
    parser.add_argument("--stop-loss-rate", type=float)
    parser.add_argument("--take-profit-rate", type=float)
    parser.add_argument(
        "--opening-range-end",
        type=_parse_time,
        default=time(9, 15),
    )
    parser.add_argument(
        "--force-exit-time",
        type=_parse_time,
        default=time(15, 30),
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--slippage-rate",
        type=float,
        default=0.0,
    )
    return parser


def load_series(
    *,
    database_path: Path,
    code: str,
    start_date: date,
    end_date: date,
) -> HistoricalBarSeries:
    """SQLiteから指定期間の5分足を読み込む。"""

    if end_date < start_date:
        raise ValueError(
            "終了日は開始日以後である必要があります。"
        )

    start_at = datetime.combine(
        start_date,
        time.min,
        tzinfo=JST,
    )
    end_at = datetime.combine(
        end_date,
        time.max,
        tzinfo=JST,
    )

    prices = MarketBarRepository(
        database_path
    ).read(
        code=code,
        interval_minutes=5,
        start_at=start_at,
        end_at=end_at,
    )

    if not prices:
        raise ValueError(
            "指定条件に一致する5分足がありません。 "
            f"code={code} from={start_date} to={end_date}"
        )

    bars = tuple(
        HistoricalBar(
            code=price.code,
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=_normalize_market_datetime(
                price.datetime
            ),
            open_price=price.open,
            high_price=price.high,
            low_price=price.low,
            close_price=price.close,
            volume=float(price.volume),
        )
        for price in prices
    )

    return HistoricalBarSeries(
        code=code,
        timeframe=MarketTimeframe.MINUTE_5,
        bars=bars,
    )


def _normalize_market_datetime(
    value: datetime,
) -> datetime:
    """市場データ日時へ日本時間を補完する。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=JST)

    return value.astimezone(JST)


def build_runner(
    *,
    series: HistoricalBarSeries,
    state_database_path: Path,
    initial_cash: float,
    strategy_settings: OrbSignalStrategySettings,
    commission: float,
    slippage_rate: float,
) -> EventDrivenBacktestRunner:
    """依存関係を組み立ててRunnerを返す。"""

    state_database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    initialize_database(state_database_path)

    initial_time = (
        series.started_at.astimezone(timezone.utc)
        if series.started_at is not None
        else datetime.now(timezone.utc)
    )
    clock = MutableClock(initial_time)

    signal_repository = SignalRepository(
        state_database_path,
        now_provider=clock.now,
    )
    order_repository = OrderRepository(
        state_database_path,
        now_provider=clock.now,
    )
    execution_repository = TradeExecutionRepository(
        state_database_path,
        now_provider=clock.now,
    )
    position_repository = PositionRepository(
        state_database_path,
        now_provider=clock.now,
    )
    portfolio_repository = PortfolioRepository(
        state_database_path,
        now_provider=clock.now,
    )

    session_id = (
        f"orb-{series.code}-"
        f"{uuid4().hex[:12]}"
    )
    strategy = OrbSignalStrategy(
        settings=strategy_settings
    )
    session = BacktestSession(
        session_id=session_id,
        strategy_runner=BacktestStrategyRunner(
            replay_engine=MarketReplayEngine(series),
            strategy=strategy,
        ),
        now_provider=clock.now,
    )

    queue = BacktestOrderQueue()
    queue_service = BacktestOrderQueueService(
        signal_repository=signal_repository,
        order_service=SignalOrderService(
            signal_repository=signal_repository,
            order_repository=order_repository,
        ),
        order_queue=queue,
        now_provider=clock.now,
    )

    latest_price = {
        series.code: series.bars[0].close_price
    }
    broker = PaperBroker(
        price_provider=lambda code: latest_price[code],
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
            commission_per_order=commission,
            slippage_rate=slippage_rate,
        ),
        now_provider=clock.now,
    )

    def update_price(code: str, price: float) -> object:
        latest_price[code] = price
        return broker.update_market_price(code, price)

    queue_execution_service = BacktestQueueExecutionService(
        order_queue=queue,
        broker_sync_service=OrderBrokerSyncService(
            order_repository=order_repository,
            broker=broker,
        ),
        execution_repository=execution_repository,
        broker_name=broker.broker_name,
        commission_per_execution=commission,
    )

    portfolio_update_service = BacktestPortfolioUpdateService(
        position_service=PositionService(
            database_path=state_database_path,
            position_repository=position_repository,
        ),
        portfolio_service=PortfolioService(
            position_repository=position_repository,
            broker=broker,
        ),
        portfolio_repository=portfolio_repository,
        equity_curve_service=EquityCurveService(
            portfolio_repository=portfolio_repository,
        ),
    )

    return EventDrivenBacktestRunner(
        session=session,
        order_queue_service=queue_service,
        queue_execution_service=queue_execution_service,
        portfolio_update_service=portfolio_update_service,
        market_price_updater=update_price,
        clock_updater=clock.set,
    )


def create_reports(
    *,
    state_database_path: Path,
    output_directory: Path,
    equity_curve_report: EquityCurveReport | None,
) -> tuple[
    BacktestTradeReport,
    BacktestPerformanceMetrics,
    BacktestReportPaths,
]:
    """保存済み約定から統計とレポートを作成する。"""

    execution_repository = TradeExecutionRepository(
        state_database_path
    )
    signal_repository = SignalRepository(
        state_database_path
    )

    trade_report = TradeReportService(
        execution_repository=execution_repository,
        signal_repository=signal_repository,
    ).create_report()

    metrics = (
        BacktestPerformanceMetricsService()
        .create_metrics(trade_report)
    )

    paths = BacktestReportWriter().write(
        output_directory=output_directory,
        trade_report=trade_report,
        metrics=metrics,
        equity_curve_report=equity_curve_report,
    )

    return trade_report, metrics, paths


def print_result(
    result: EventDrivenBacktestRunResult,
    *,
    state_database_path: Path,
    trade_report: BacktestTradeReport,
    metrics: BacktestPerformanceMetrics,
    report_paths: BacktestReportPaths,
) -> None:
    """バックテスト結果と分析指標を表示する。"""

    report = result.equity_curve_report

    print("Project KATANA ORB Backtest")
    print(f"frames: {result.frame_count}")
    print(f"signals: {result.signal_count}")
    print(f"orders: {result.queued_count}")
    print(f"executions: {result.execution_count}")
    print(
        f"portfolio_updates: "
        f"{result.portfolio_update_count}"
    )
    print(f"trades: {metrics.trade_count}")
    print(
        "win_rate: "
        + (
            "N/A"
            if metrics.win_rate is None
            else f"{metrics.win_rate:.2%}"
        )
    )
    print(
        "profit_factor: "
        + (
            "N/A"
            if metrics.profit_factor is None
            else f"{metrics.profit_factor:.4f}"
        )
    )
    print(
        "expectancy: "
        + (
            "N/A"
            if metrics.expectancy is None
            else f"{metrics.expectancy:.2f}"
        )
    )
    print(
        f"net_profit_loss: "
        f"{metrics.net_profit_loss:.2f}"
    )
    print(
        f"maximum_consecutive_wins: "
        f"{metrics.maximum_consecutive_wins}"
    )
    print(
        f"maximum_consecutive_losses: "
        f"{metrics.maximum_consecutive_losses}"
    )
    print(
        f"unmatched_buy_quantity: "
        f"{trade_report.unmatched_buy_quantity}"
    )
    print(
        f"unmatched_sell_quantity: "
        f"{trade_report.unmatched_sell_quantity}"
    )

    if report is not None:
        print(f"initial_equity: {report.initial_equity:.2f}")
        print(f"final_equity: {report.final_equity:.2f}")
        print(
            f"total_return_rate: "
            f"{report.total_return:.4f}"
        )
        print(
            f"maximum_drawdown_rate: "
            f"{report.maximum_drawdown:.4f}"
        )

    print(f"state_database: {state_database_path}")
    print(
        f"report_directory: "
        f"{report_paths.output_directory}"
    )
    print(f"trades_csv: {report_paths.trades_csv}")
    print(
        f"equity_curve_csv: "
        f"{report_paths.equity_curve_csv}"
    )
    print(f"metrics_csv: {report_paths.metrics_csv}")
    print(f"summary_json: {report_paths.summary_json}")


def run_best_backtest(
    *,
    series: HistoricalBarSeries,
    report_directory: Path,
    initial_cash: float,
    quantity: int,
    force_exit_time: time,
    commission: float,
    slippage_rate: float,
    parameter: OrbOptimizationParameters,
) -> None:
    """最良パラメータで追試バックテストを実行する。"""

    output_directory = report_directory / "best_backtest"
    state_database_path = output_directory / "state.db"

    runner = build_runner(
        series=series,
        state_database_path=state_database_path,
        initial_cash=initial_cash,
        strategy_settings=OrbSignalStrategySettings(
            quantity=quantity,
            opening_range_end=parameter.opening_range_end,
            force_exit_time=force_exit_time,
            stop_loss_rate=parameter.stop_loss_rate,
            take_profit_rate=parameter.take_profit_rate,
        ),
        commission=commission,
        slippage_rate=slippage_rate,
    )
    result = runner.run()

    trade_report, metrics, report_paths = create_reports(
        state_database_path=state_database_path,
        output_directory=output_directory,
        equity_curve_report=result.equity_curve_report,
    )

    print("Applied Best Parameter Backtest")
    print(f"parameter_id: {parameter.parameter_id}")
    print_result(
        result,
        state_database_path=state_database_path,
        trade_report=trade_report,
        metrics=metrics,
        report_paths=report_paths,
    )


def run_optimization(
    *,
    series: HistoricalBarSeries,
    report_directory: Path,
    initial_cash: float,
    quantity: int,
    force_exit_time: time,
    commission: float,
    slippage_rate: float,
    stop_loss_candidates: tuple[float | None, ...],
    take_profit_candidates: tuple[float | None, ...],
    opening_range_end_candidates: tuple[time, ...],
    ranking_method: str,
    top_n: int,
    composite_weights: CompositeScoreWeights,
    save_best: bool = False,
    apply_best: bool = False,
) -> int:
    """ORBパラメータ最適化を実行する。"""

    if top_n <= 0:
        raise ValueError(
            "top-nは0より大きい必要があります。"
        )

    grid = OrbOptimizationGridService().create_grid(
        stop_loss_rates=stop_loss_candidates,
        take_profit_rates=take_profit_candidates,
        opening_range_ends=opening_range_end_candidates,
    )
    runs_directory = report_directory / "runs"

    def executor(
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        run_directory = (
            runs_directory / parameter.parameter_id
        )
        state_database_path = (
            run_directory / "state.db"
        )

        runner = build_runner(
            series=series,
            state_database_path=state_database_path,
            initial_cash=initial_cash,
            strategy_settings=OrbSignalStrategySettings(
                quantity=quantity,
                opening_range_end=(
                    parameter.opening_range_end
                ),
                force_exit_time=force_exit_time,
                stop_loss_rate=(
                    parameter.stop_loss_rate
                ),
                take_profit_rate=(
                    parameter.take_profit_rate
                ),
            ),
            commission=commission,
            slippage_rate=slippage_rate,
        )
        result = runner.run()

        (
            trade_report,
            metrics,
            _paths,
        ) = create_reports(
            state_database_path=state_database_path,
            output_directory=run_directory,
            equity_curve_report=result.equity_curve_report,
        )

        if (
            trade_report.unmatched_buy_quantity > 0
            or trade_report.unmatched_sell_quantity > 0
        ):
            raise RuntimeError(
                "最適化試行に未対応約定が残っています。"
            )

        return OrbOptimizationExecutionOutput(
            metrics=metrics,
            equity_curve_report=(
                result.equity_curve_report
            ),
        )

    optimization_result = OrbOptimizationRunner(
        executor=executor
    ).run(
        grid,
        continue_on_error=True,
    )

    normalized_method = ranking_method.strip().lower()
    composite_score_report = None
    report_weights = None

    if normalized_method == COMPOSITE_RANKING:
        composite_score_report = (
            CompositeOptimizationScoreService()
            .create_report(
                optimization_result,
                weights=composite_weights,
            )
        )
        ranking = (
            CompositeOptimizationRankingService()
            .rank(
                composite_score_report,
                top_n=top_n,
            )
        )
        report_weights = composite_weights
    else:
        metric = RankingMetric(normalized_method)
        ranking = OptimizationRankingService().rank(
            optimization_result,
            metric=metric,
            top_n=top_n,
        )

    should_save_best = save_best or apply_best
    paths = OptimizationReportWriter().write(
        output_directory=report_directory,
        result=optimization_result,
        ranking=ranking,
        ranking_method=normalized_method,
        composite_score_report=composite_score_report,
        weights=report_weights,
        save_best=should_save_best,
    )

    print("Project KATANA ORB Optimization")
    print(f"combinations: {grid.combination_count}")
    print(
        f"completed: "
        f"{optimization_result.completed_count}"
    )
    print(
        f"failed: "
        f"{optimization_result.failed_count}"
    )
    print(f"ranking_method: {normalized_method}")

    if normalized_method == COMPOSITE_RANKING:
        for item in ranking.items:
            run = item.item.run
            components = item.item.components

            print(
                f"rank={item.rank} "
                f"parameter={item.parameter_id} "
                f"composite_score={item.score:.6f} "
                f"net_profit_score="
                f"{components.net_profit:.6f} "
                f"profit_factor_score="
                f"{components.profit_factor:.6f} "
                f"win_rate_score="
                f"{components.win_rate:.6f} "
                f"drawdown_score="
                f"{components.maximum_drawdown:.6f} "
                f"net_profit={run.net_profit_loss} "
                f"profit_factor={run.profit_factor} "
                f"win_rate={run.win_rate} "
                f"max_drawdown={run.maximum_drawdown}"
            )
    else:
        for item in ranking:
            print(
                f"rank={item.rank} "
                f"parameter={item.run.parameter_id} "
                f"net_profit={item.run.net_profit_loss} "
                f"profit_factor={item.run.profit_factor} "
                f"win_rate={item.run.win_rate} "
                f"max_drawdown={item.run.maximum_drawdown}"
            )

    print(
        f"optimization_csv: "
        f"{paths.optimization_csv}"
    )
    print(
        f"optimization_json: "
        f"{paths.optimization_json}"
    )

    if paths.best_parameters_json is not None:
        print(
            f"best_parameters_json: "
            f"{paths.best_parameters_json}"
        )

    if apply_best:
        best_run = OptimizationReportWriter.best_run(
            ranking
        )

        if best_run is None:
            raise RuntimeError(
                "追試へ適用できる最良パラメータがありません。"
            )

        run_best_backtest(
            series=series,
            report_directory=report_directory,
            initial_cash=initial_cash,
            quantity=quantity,
            force_exit_time=force_exit_time,
            commission=commission,
            slippage_rate=slippage_rate,
            parameter=best_run.parameter,
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLIエントリーポイント。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    if (args.save_best or args.apply_best) and not args.optimize:
        parser.error(
            "--save-bestと--apply-bestは"
            "--optimizeと一緒に指定してください。"
        )

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    series = load_series(
        database_path=args.database,
        code=args.code,
        start_date=start_date,
        end_date=end_date,
    )

    run_token = uuid4().hex[:12]
    report_prefix = (
        "optimization"
        if args.optimize
        else "backtest"
    )
    report_directory = (
        args.report_dir
        if args.report_dir is not None
        else settings.reports_dir
        / (
            f"{report_prefix}_{args.code}_"
            f"{run_token}"
        )
    )

    if args.optimize:
        ranking_method = (
            args.ranking
            if args.ranking is not None
            else args.optimization_metric
        )

        return run_optimization(
            series=series,
            report_directory=report_directory,
            initial_cash=args.initial_cash,
            quantity=args.quantity,
            force_exit_time=args.force_exit_time,
            commission=args.commission,
            slippage_rate=args.slippage_rate,
            stop_loss_candidates=(
                _parse_rate_candidates(
                    args.stop_loss_candidates
                )
            ),
            take_profit_candidates=(
                _parse_rate_candidates(
                    args.take_profit_candidates
                )
            ),
            opening_range_end_candidates=(
                _parse_time_candidates(
                    args.opening_range_end_candidates
                )
            ),
            ranking_method=ranking_method,
            top_n=args.optimization_top_n,
            composite_weights=CompositeScoreWeights(
                net_profit=args.weight_net_profit,
                profit_factor=args.weight_profit_factor,
                win_rate=args.weight_win_rate,
                maximum_drawdown=args.weight_drawdown,
            ),
            save_best=args.save_best,
            apply_best=args.apply_best,
        )

    state_database_path = (
        args.state_database
        if args.state_database is not None
        else report_directory / "state.db"
    )

    runner = build_runner(
        series=series,
        state_database_path=state_database_path,
        initial_cash=args.initial_cash,
        strategy_settings=OrbSignalStrategySettings(
            quantity=args.quantity,
            opening_range_end=args.opening_range_end,
            force_exit_time=args.force_exit_time,
            stop_loss_rate=args.stop_loss_rate,
            take_profit_rate=args.take_profit_rate,
        ),
        commission=args.commission,
        slippage_rate=args.slippage_rate,
    )
    result = runner.run()

    (
        trade_report,
        metrics,
        report_paths,
    ) = create_reports(
        state_database_path=state_database_path,
        output_directory=report_directory,
        equity_curve_report=result.equity_curve_report,
    )

    print_result(
        result,
        state_database_path=state_database_path,
        trade_report=trade_report,
        metrics=metrics,
        report_paths=report_paths,
    )
    return 0


def _parse_rate_candidates(
    value: str,
) -> tuple[float | None, ...]:
    """カンマ区切り率候補を解析する。"""

    candidates: list[float | None] = []

    for raw in value.split(","):
        normalized = raw.strip().lower()

        if not normalized:
            continue

        if normalized in {"none", "null"}:
            candidates.append(None)
        else:
            candidates.append(float(normalized))

    if not candidates:
        raise ValueError(
            "率候補を1件以上指定してください。"
        )

    return tuple(candidates)


def _parse_time_candidates(
    value: str,
) -> tuple[time, ...]:
    """カンマ区切り時刻候補を解析する。"""

    candidates = tuple(
        _parse_time(raw.strip())
        for raw in value.split(",")
        if raw.strip()
    )

    if not candidates:
        raise ValueError(
            "時刻候補を1件以上指定してください。"
        )

    return candidates


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "日付はYYYY-MM-DD形式で指定してください。"
        ) from error


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "時刻はHH:MM形式で指定してください。"
        ) from error


if __name__ == "__main__":
    raise SystemExit(main())
