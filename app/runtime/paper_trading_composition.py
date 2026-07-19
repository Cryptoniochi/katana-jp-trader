"""本番Paper Tradingの依存関係を一か所で組み立てる。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.application.trading_loop_component import (
    TradingLoopComponent,
)
from app.application.trading_loop_service import (
    TradingLoopService,
)
from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioUpdateService,
)
from app.backtest.order_queue import BacktestOrderQueue
from app.backtest.order_queue_service import (
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionService,
)
from app.database import initialize_database
from app.live.live_orchestrator import (
    LiveTradingOrchestrator,
)
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.jquants_downloader import (
    JQuantsMinuteDownloader,
)
from app.market.market_calendar import TokyoMarketCalendar
from app.market.market_clock import TokyoMarketClock
from app.market.models import StockPrice
from app.market.realtime_market_service import (
    RealtimeMarketMonitor,
    TokyoMarketSessionService,
)
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingService,
)
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDaySettings,
)
from app.runtime.paper_trading_day_service import (
    PaperTradingDayService,
)
from app.runtime.paper_trading_runtime_factory import (
    PaperTradingRuntimeBundle,
    PaperTradingRuntimeFactory,
)
from app.runtime.session_service import RuntimeSessionService
from app.trading.equity_curve_service import (
    EquityCurveService,
)
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncService,
)
from app.trading.order_repository import OrderRepository
from app.trading.order_service import SignalOrderService
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.paper_broker_recovery_service import (
    PaperBrokerRecoveryResult,
    PaperBrokerRecoveryService,
)
from app.trading.portfolio_repository import (
    PortfolioRepository,
)
from app.trading.portfolio_service import PortfolioService
from app.trading.position_repository import (
    PositionRepository,
)
from app.trading.position_service import PositionService
from app.trading.signal_repository import SignalRepository
from app.trading.trade_execution_repository import (
    TradeExecutionRepository,
)


NowProvider = Callable[[], datetime]
StopPredicate = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class PaperTradingProductionSettings:
    """本番Paper TradingのComposition設定。"""

    database_path: Path
    codes: tuple[str, ...]
    initial_cash: float = 10_000_000.0
    cycle_interval_seconds: float = 30.0
    maximum_cycles: int | None = None
    jquants_api_key: str | None = None
    jquants_timeout_seconds: float = 30.0
    commission_per_order: float = 0.0
    slippage_rate: float = 0.0
    continue_on_cycle_error: bool = True
    stop_on_cycle_failure: bool = False
    stop_on_resource_critical: bool = True

    def __post_init__(self) -> None:
        """設定値を正規化して検証する。"""

        database_path = Path(self.database_path)
        normalized_codes = tuple(
            dict.fromkeys(
                code.strip()
                for code in self.codes
                if code.strip()
            )
        )

        if not normalized_codes:
            raise ValueError(
                "監視対象銘柄を1件以上指定してください。"
            )

        for code in normalized_codes:
            if not code.isdigit():
                raise ValueError(
                    "銘柄コードは数字で指定してください。 "
                    f"value={code}"
                )

            if len(code) not in {4, 5}:
                raise ValueError(
                    "銘柄コードは4桁または5桁で"
                    "指定してください。 "
                    f"value={code}"
                )

        if self.initial_cash < 0:
            raise ValueError(
                "初期資金は0以上である必要があります。"
            )

        if self.cycle_interval_seconds < 0:
            raise ValueError(
                "サイクル間隔は0秒以上である必要があります。"
            )

        if (
            self.maximum_cycles is not None
            and self.maximum_cycles <= 0
        ):
            raise ValueError(
                "最大サイクル数は0より大きい必要があります。"
            )

        if self.jquants_timeout_seconds <= 0:
            raise ValueError(
                "J-Quantsタイムアウト秒数は"
                "0より大きい必要があります。"
            )

        if self.commission_per_order < 0:
            raise ValueError(
                "注文手数料は0以上である必要があります。"
            )

        if self.slippage_rate < 0:
            raise ValueError(
                "スリッページ率は0以上である必要があります。"
            )

        object.__setattr__(
            self,
            "database_path",
            database_path,
        )
        object.__setattr__(
            self,
            "codes",
            normalized_codes,
        )


@dataclass(frozen=True, slots=True)
class PaperTradingProductionBundle:
    """本番Paper Tradingで生成した主要Component一式。"""

    settings: PaperTradingProductionSettings
    day_service: PaperTradingDayService
    trading_loop_component: TradingLoopComponent
    runtime_bundle: PaperTradingRuntimeBundle
    market_monitor: RealtimeMarketMonitor
    paper_broker: PaperBroker
    broker_recovery_result: PaperBrokerRecoveryResult
    portfolio_service: PortfolioService

    def run(self) -> PaperTradingDayResult:
        """Trading Loopを開始して終日運用を実行する。"""

        self.trading_loop_component.start()

        try:
            return self.day_service.run()
        finally:
            if self.trading_loop_component.is_running:
                self.trading_loop_component.stop()


class PaperTradingComposition:
    """本番Paper TradingのComposition Root。"""

    @staticmethod
    def create(
        *,
        settings: PaperTradingProductionSettings,
        now_provider: NowProvider | None = None,
        stop_requested: StopPredicate | None = None,
    ) -> PaperTradingProductionBundle:
        """実運用に必要な依存関係をすべて生成する。"""

        resolved_now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        resolved_stop_requested = (
            stop_requested
            if stop_requested is not None
            else lambda: False
        )

        settings.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        initialize_database(settings.database_path)

        market_bar_repository = MarketBarRepository(
            settings.database_path
        )
        downloader = JQuantsMinuteDownloader(
            api_key=settings.jquants_api_key,
            timeout_seconds=(
                settings.jquants_timeout_seconds
            ),
        )
        aggregator = StockPriceAggregator()

        def provide_five_minute_bars(
            code: str,
            target_date: date,
        ) -> list[StockPrice]:
            minute_bars = downloader.download(
                code,
                target_date.isoformat(),
            )

            return aggregator.aggregate_to_five_minutes(
                minute_bars
            )

        market_calendar = TokyoMarketCalendar()
        market_session_service = TokyoMarketSessionService(
            trading_day_predicate=(
                market_calendar.is_business_day
            )
        )
        market_monitor = RealtimeMarketMonitor(
            repository=market_bar_repository,
            bar_provider=provide_five_minute_bars,
            session_service=market_session_service,
            interval_minutes=5,
            data_source="jquants-realtime",
        )

        signal_repository = SignalRepository(
            settings.database_path,
            now_provider=resolved_now_provider,
        )
        order_repository = OrderRepository(
            settings.database_path,
            now_provider=resolved_now_provider,
        )
        execution_repository = TradeExecutionRepository(
            settings.database_path,
            now_provider=resolved_now_provider,
        )
        position_repository = PositionRepository(
            settings.database_path,
            now_provider=resolved_now_provider,
        )
        portfolio_repository = PortfolioRepository(
            settings.database_path,
            now_provider=resolved_now_provider,
        )

        market_prices: dict[str, float] = {}

        def provide_market_price(code: str) -> float:
            normalized_code = code.strip()

            try:
                return market_prices[normalized_code]
            except KeyError as error:
                raise RuntimeError(
                    "Paper Brokerへ渡す現在価格が"
                    "まだ登録されていません。 "
                    f"code={normalized_code}"
                ) from error

        paper_broker = PaperBroker(
            price_provider=provide_market_price,
            settings=PaperBrokerSettings(
                initial_cash=settings.initial_cash,
                commission_per_order=(
                    settings.commission_per_order
                ),
                slippage_rate=settings.slippage_rate,
                broker_name="paper",
            ),
            now_provider=resolved_now_provider,
        )

        broker_recovery_result = (
            PaperBrokerRecoveryService(
                broker=paper_broker,
                order_repository=order_repository,
                position_repository=position_repository,
                portfolio_repository=portfolio_repository,
            ).recover()
        )

        for restored_position in (
            paper_broker.list_positions()
        ):
            market_prices[
                restored_position.code
            ] = restored_position.market_price

        def update_market_price(
            code: str,
            price: float,
        ) -> object:
            normalized_code = code.strip()
            normalized_price = float(price)

            market_prices[normalized_code] = normalized_price

            return paper_broker.update_market_price(
                normalized_code,
                normalized_price,
            )

        signal_order_service = SignalOrderService(
            signal_repository=signal_repository,
            order_repository=order_repository,
        )
        order_queue = BacktestOrderQueue()
        order_queue_service = BacktestOrderQueueService(
            signal_repository=signal_repository,
            order_service=signal_order_service,
            order_queue=order_queue,
            now_provider=resolved_now_provider,
        )
        broker_sync_service = OrderBrokerSyncService(
            order_repository=order_repository,
            broker=paper_broker,
        )
        queue_execution_service = (
            BacktestQueueExecutionService(
                order_queue=order_queue,
                broker_sync_service=broker_sync_service,
                execution_repository=execution_repository,
                broker_name=paper_broker.broker_name,
                commission_per_execution=(
                    settings.commission_per_order
                ),
                slippage_per_execution=0.0,
            )
        )

        position_service = PositionService(
            database_path=settings.database_path,
            position_repository=position_repository,
        )
        portfolio_service = PortfolioService(
            position_repository=position_repository,
            broker=paper_broker,
        )
        equity_curve_service = EquityCurveService(
            portfolio_repository=portfolio_repository,
        )
        portfolio_update_service = (
            BacktestPortfolioUpdateService(
                position_service=position_service,
                portfolio_service=portfolio_service,
                portfolio_repository=portfolio_repository,
                equity_curve_service=equity_curve_service,
            )
        )

        realtime_paper_trading_service = (
            RealtimePaperTradingService(
                signal_engine=RealtimeSignalEngine(),
                order_queue_service=order_queue_service,
                queue_execution_service=(
                    queue_execution_service
                ),
                portfolio_update_service=(
                    portfolio_update_service
                ),
                market_price_updater=update_market_price,
            )
        )
        live_orchestrator = LiveTradingOrchestrator(
            market_monitor=market_monitor,
            paper_trading_service=(
                realtime_paper_trading_service
            ),
            now_provider=resolved_now_provider,
        )

        runtime_session = RuntimeSessionService(
            now_provider=resolved_now_provider,
        )
        trading_loop_service = TradingLoopService(
            live_orchestrator=live_orchestrator,
            runtime_session=runtime_session,
            resource_integration=None,
            now_provider=resolved_now_provider,
        )
        trading_loop_component = TradingLoopComponent(
            service=trading_loop_service,
            runtime_session=runtime_session,
            codes=settings.codes,
            continue_on_error=(
                settings.continue_on_cycle_error
            ),
            continue_on_notification_error=True,
        )

        runtime_bundle = PaperTradingRuntimeFactory.create(
            database_path=settings.database_path,
            cycle_runner=trading_loop_component,
            portfolio_reader=portfolio_service,
            now_provider=resolved_now_provider,
        )

        day_service = PaperTradingDayService(
            runtime=runtime_bundle.runtime,
            persistence_service=(
                runtime_bundle.persistence_service
            ),
            market_clock=TokyoMarketClock(
                calendar=market_calendar
            ),
            dashboard_publisher=None,
            post_run_hooks=(),
            settings=PaperTradingDaySettings(
                cycle_interval_seconds=(
                    settings.cycle_interval_seconds
                ),
                maximum_cycles=settings.maximum_cycles,
                stop_on_cycle_failure=(
                    settings.stop_on_cycle_failure
                ),
                stop_on_resource_critical=(
                    settings.stop_on_resource_critical
                ),
                continue_on_dashboard_error=True,
                continue_on_post_run_hook_error=True,
            ),
            now_provider=resolved_now_provider,
            stop_requested=resolved_stop_requested,
        )

        return PaperTradingProductionBundle(
            settings=settings,
            day_service=day_service,
            trading_loop_component=(
                trading_loop_component
            ),
            runtime_bundle=runtime_bundle,
            market_monitor=market_monitor,
            paper_broker=paper_broker,
            broker_recovery_result=(
                broker_recovery_result
            ),
            portfolio_service=portfolio_service,
        )
