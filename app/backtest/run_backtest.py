"""保存済み5分足でORBバックテストを実行するCLI。"""

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
from app.backtest.backtest_session import BacktestSession
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
from app.backtest.orb_signal_strategy import (
    OrbSignalStrategy,
    OrbSignalStrategySettings,
)
from app.backtest.order_queue import BacktestOrderQueue
from app.backtest.order_queue_service import (
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionService,
)
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
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
        "--initial-cash",
        type=float,
        default=10_000_000.0,
    )
    parser.add_argument("--quantity", type=int, default=100)
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


def print_result(
    result: EventDrivenBacktestRunResult,
    *,
    state_database_path: Path,
) -> None:
    """バックテスト結果を標準出力へ表示する。"""

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


def main(argv: list[str] | None = None) -> int:
    """CLIエントリーポイント。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    series = load_series(
        database_path=args.database,
        code=args.code,
        start_date=start_date,
        end_date=end_date,
    )

    state_database_path = (
        args.state_database
        if args.state_database is not None
        else settings.reports_dir
        / (
            f"backtest_{args.code}_"
            f"{uuid4().hex[:12]}.db"
        )
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
    print_result(
        result,
        state_database_path=state_database_path,
    )
    return 0


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
