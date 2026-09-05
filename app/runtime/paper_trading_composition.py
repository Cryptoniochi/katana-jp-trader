"""本番Paper Tradingの依存関係を一か所で組み立てる。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.dynamic_watchlist.strategy_routing_models import (
    StrategyRoutingSnapshot,
)
from app.dynamic_watchlist.strategy_routing_repository import (
    DynamicWatchlistStrategyRoutingError,
    DynamicWatchlistStrategyRoutingRepository,
)
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
from app.risk.risk_aware_queue_execution_service import (
    RiskAwareQueueExecutionService,
)
from app.risk.paper_trading_pretrade_risk import (
    PaperTradingPreTradeRiskProvider,
    PaperTradingRiskLimits,
)
from app.risk.paper_trading_trace import (
    PaperTradingTraceRecorder,
)
from app.database import initialize_database
from app.live.live_orchestrator import (
    LiveTradingOrchestrator,
)
from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_completed_bar_provider import (
    KabuStationCompletedBarProvider,
)
from app.market.kabu_station_realtime_provider import (
    KabuStationRealtimeProvider,
)
from app.market.kabu_station_realtime_service import (
    KabuStationRealtimeService,
)
from app.market.kabu_station_websocket import (
    KabuStationWebSocketClient,
)
from app.notifications.execution_notification_service import (
    ExecutionNotificationService,
)
from app.notifications.notification_composition import (
    NotificationComposition,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)
from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateRepository,
)
from app.settings import ROOT_DIR, Settings
from app.market.bar_repository import MarketBarRepository
from app.market.market_calendar import TokyoMarketCalendar
from app.market.market_clock import TokyoMarketClock
from app.market.realtime_market_service import (
    RealtimeMarketMonitor,
    TokyoMarketSessionService,
)
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingService,
)
from app.market.high_breakout_candidate_provider import (
    RepositoryHighBreakoutCandidateProvider,
)
from app.market.symbol_strategy_router import (
    SymbolStrategyRouter,
)
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
)
from app.runtime.end_of_day_liquidation_service import (
    EndOfDayLiquidationService,
)
from app.runtime.watchlist_execution_integrity_post_run_hook import (
    WatchlistExecutionIntegrityPostRunHook,
)
from app.runtime.watchlist_execution_integrity_service import (
    WatchlistExecutionIntegrityService,
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
from app.watchlist import WatchlistError, load_watchlist


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
    enabled_strategy_names: tuple[str, ...] = ("orb",)
    strategy_routing_enabled: bool = True
    strategy_routing_report_path: Path = Path(
        "reports/watchlist/latest.json"
    )
    strategy_routing_minimum_rating_tier: str = "C"
    strategy_routing_minimum_total_score: float = 0.0
    strategy_routing_fail_open: bool = True
    maximum_codes_per_poll: int = 10
    rate_limit_cooldown_seconds: float = 60.0
    market_data_mode: str = "kabu-station-realtime"
    kabu_station_api_password: str | None = None
    kabu_station_base_url: str = (
        "http://localhost:18080/kabusapi"
    )
    kabu_station_websocket_url: str = (
        "ws://localhost:18080/kabusapi/websocket"
    )
    commission_per_order: float = 0.0
    slippage_rate: float = 0.0
    continue_on_cycle_error: bool = True
    stop_on_cycle_failure: bool = False
    stop_on_resource_critical: bool = True
    max_position_count: int = 5
    max_position_value: float = 1_000_000.0
    max_total_exposure: float = 5_000_000.0
    minimum_cash_balance: float = 500_000.0
    max_daily_loss: float = 100_000.0
    max_daily_entries: int = 5
    risk_trace_enabled: bool = True
    risk_trace_path: Path = Path(
        "logs/risk/paper_trading_trace.jsonl"
    )
    watchlist_path: Path = Path("watchlist.txt")
    watchlist_explainability_path: Path = Path(
        "reports/watchlist/explainability/latest.json"
    )
    watchlist_execution_integrity_report_path: Path = Path(
        "reports/service/watchlist_execution_integrity.json"
    )

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

        normalized_strategy_names = tuple(
            dict.fromkeys(
                name.strip().lower()
                for name in self.enabled_strategy_names
                if name.strip()
            )
        )

        if not normalized_strategy_names:
            raise ValueError(
                "有効戦略を1件以上指定してください。"
            )

        unknown_strategies = tuple(
            name
            for name in normalized_strategy_names
            if name not in {"orb", "pullback", "high-breakout"}
        )

        if unknown_strategies:
            raise ValueError(
                "未対応の戦略が指定されています。 "
                f"strategies={','.join(unknown_strategies)}"
            )

        if self.strategy_routing_minimum_rating_tier not in {
            "A+",
            "A",
            "B",
            "C",
        }:
            raise ValueError(
                "戦略ルーティング最低Tierは"
                "A+、A、B、Cのいずれかです。"
            )

        if self.strategy_routing_minimum_total_score < 0:
            raise ValueError(
                "戦略ルーティング最低総合スコアは"
                "0以上である必要があります。"
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

        if self.maximum_codes_per_poll <= 0:
            raise ValueError(
                "1回の最大取得銘柄数は"
                "0より大きい必要があります。"
            )

        if self.rate_limit_cooldown_seconds < 0:
            raise ValueError(
                "レート制限待機秒数は0以上である必要があります。"
            )

        normalized_market_data_mode = (
            self.market_data_mode.strip().lower()
        )

        if normalized_market_data_mode != "kabu-station-realtime":
            raise ValueError(
                "市場データモードはkabu-station-realtimeのみ"
                "指定できます。"
            )

        normalized_kabu_base_url = (
            self.kabu_station_base_url.strip().rstrip("/")
        )
        normalized_kabu_websocket_url = (
            self.kabu_station_websocket_url.strip()
        )

        if not normalized_kabu_base_url:
            raise ValueError(
                "kabuステーションBase URLを指定してください。"
            )

        if not normalized_kabu_websocket_url:
            raise ValueError(
                "kabuステーションWebSocket URLを"
                "指定してください。"
            )

        if (
            normalized_market_data_mode
            == "kabu-station-realtime"
            and not (
                self.kabu_station_api_password
                and self.kabu_station_api_password.strip()
            )
        ):
            raise ValueError(
                "kabu-station-realtimeには環境変数"
                "KABU_STATION_API_PASSWORDが必要です。"
            )

        if (
            normalized_market_data_mode
            == "kabu-station-realtime"
            and len(normalized_codes) > 50
        ):
            raise ValueError(
                "kabuステーションAPIの登録上限は"
                "50銘柄です。"
            )

        if self.max_position_count <= 0:
            raise ValueError(
                "最大保有銘柄数は0より大きい必要があります。"
            )

        if self.max_daily_entries <= 0:
            raise ValueError(
                "1日最大エントリー数は0より大きい必要があります。"
            )

        for name, value in {
            "1銘柄最大投資額": self.max_position_value,
            "最大総投資額": self.max_total_exposure,
            "最低現金残高": self.minimum_cash_balance,
            "日次損失上限": self.max_daily_loss,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if self.commission_per_order < 0:
            raise ValueError(
                "注文手数料は0以上である必要があります。"
            )

        if self.slippage_rate < 0:
            raise ValueError(
                "スリッページ率は0以上である必要があります。"
            )

        normalized_strategy_routing_report_path = Path(
            self.strategy_routing_report_path
        )

        if not normalized_strategy_routing_report_path.is_absolute():
            normalized_strategy_routing_report_path = (
                ROOT_DIR
                / normalized_strategy_routing_report_path
            )

        normalized_risk_trace_path = Path(
            self.risk_trace_path
        )

        if not normalized_risk_trace_path.is_absolute():
            normalized_risk_trace_path = (
                ROOT_DIR / normalized_risk_trace_path
            )

        normalized_watchlist_path = Path(
            self.watchlist_path
        )
        if not normalized_watchlist_path.is_absolute():
            normalized_watchlist_path = (
                ROOT_DIR / normalized_watchlist_path
            )

        normalized_watchlist_explainability_path = Path(
            self.watchlist_explainability_path
        )
        if not normalized_watchlist_explainability_path.is_absolute():
            normalized_watchlist_explainability_path = (
                ROOT_DIR
                / normalized_watchlist_explainability_path
            )

        normalized_watchlist_execution_integrity_report_path = Path(
            self.watchlist_execution_integrity_report_path
        )
        if (
            not normalized_watchlist_execution_integrity_report_path
            .is_absolute()
        ):
            normalized_watchlist_execution_integrity_report_path = (
                ROOT_DIR
                / normalized_watchlist_execution_integrity_report_path
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
        object.__setattr__(
            self,
            "enabled_strategy_names",
            normalized_strategy_names,
        )
        object.__setattr__(
            self,
            "market_data_mode",
            normalized_market_data_mode,
        )
        object.__setattr__(
            self,
            "kabu_station_base_url",
            normalized_kabu_base_url,
        )
        object.__setattr__(
            self,
            "kabu_station_websocket_url",
            normalized_kabu_websocket_url,
        )
        object.__setattr__(
            self,
            "strategy_routing_report_path",
            normalized_strategy_routing_report_path.resolve(),
        )
        object.__setattr__(
            self,
            "risk_trace_path",
            normalized_risk_trace_path.resolve(),
        )
        object.__setattr__(
            self,
            "watchlist_path",
            normalized_watchlist_path.resolve(),
        )
        object.__setattr__(
            self,
            "watchlist_explainability_path",
            normalized_watchlist_explainability_path.resolve(),
        )
        object.__setattr__(
            self,
            "watchlist_execution_integrity_report_path",
            normalized_watchlist_execution_integrity_report_path.resolve(),
        )


class RuntimeWatchlistSynchronizer:
    """Watchlistと保有銘柄から稼働中Universeを同期する。"""

    def __init__(
        self,
        *,
        watchlist_path: Path,
        trading_loop_component: TradingLoopComponent,
        kabu_station_service: KabuStationRealtimeService,
        paper_broker: PaperBroker,
        maximum_registered_symbols: int = 50,
    ) -> None:
        if maximum_registered_symbols <= 0:
            raise ValueError(
                "最大登録銘柄数は0より大きい必要があります。"
            )
        self.watchlist_path = Path(watchlist_path)
        self.trading_loop_component = trading_loop_component
        self.kabu_station_service = kabu_station_service
        self.paper_broker = paper_broker
        self.maximum_registered_symbols = maximum_registered_symbols
        self._last_watchlist_codes: tuple[str, ...] | None = None

    def synchronize(self) -> tuple[str, ...]:
        """変更時だけ保有銘柄優先でRuntime Universeを同期する。"""

        try:
            watchlist_codes = tuple(
                load_watchlist(self.watchlist_path)
            )
        except (FileNotFoundError, WatchlistError):
            return self.trading_loop_component.codes

        if not watchlist_codes:
            return self.trading_loop_component.codes

        position_codes = tuple(
            dict.fromkeys(
                str(position.code).strip()
                for position in self.paper_broker.list_positions()
                if str(position.code).strip()
            )
        )
        runtime_codes = tuple(
            dict.fromkeys((*position_codes, *watchlist_codes))
        )[: self.maximum_registered_symbols]

        if (
            watchlist_codes == self._last_watchlist_codes
            and runtime_codes == self.trading_loop_component.codes
        ):
            return runtime_codes

        self.kabu_station_service.update_registered_codes(runtime_codes)
        self.trading_loop_component.update_codes(runtime_codes)
        self._last_watchlist_codes = watchlist_codes
        return runtime_codes


class RuntimeStrategyRoutingSynchronizer:
    """Dynamic Watchlistの戦略RoutingをCycle境界で同期する。"""

    def __init__(
        self,
        *,
        repository: DynamicWatchlistStrategyRoutingRepository,
        signal_engine: RealtimeSignalEngine,
        current_snapshot: StrategyRoutingSnapshot | None = None,
        fail_open: bool = True,
    ) -> None:
        self.repository = repository
        self.signal_engine = signal_engine
        self.current_snapshot = current_snapshot
        self.fail_open = fail_open

    def synchronize(
        self,
    ) -> StrategyRoutingSnapshot | None:
        """有効な新SnapshotだけをSignal Engineへ反映する。"""

        try:
            snapshot = self.repository.load()
        except DynamicWatchlistStrategyRoutingError:
            if self.fail_open:
                return self.current_snapshot
            raise

        if self._routing_signature(snapshot) == self._routing_signature(
            self.current_snapshot
        ):
            return self.current_snapshot

        router = SymbolStrategyRouter(snapshot)
        self.signal_engine.update_symbol_strategy_router(router)
        self.current_snapshot = snapshot
        return snapshot

    @staticmethod
    def _routing_signature(
        snapshot: StrategyRoutingSnapshot | None,
    ) -> tuple[object, ...] | None:
        if snapshot is None:
            return None

        return (
            snapshot.fallback_strategy_names,
            tuple(
                (
                    route.code,
                    route.strategy_name,
                    route.rating_tier,
                    route.total_score,
                    route.strategy_score,
                )
                for route in snapshot.routes
            ),
        )


class RuntimeWatchlistCycleRunner:
    """各Trading Cycle直前にRuntime Watchlistを同期する。"""

    def __init__(
        self,
        *,
        cycle_runner: TradingLoopComponent,
        synchronizer: RuntimeWatchlistSynchronizer,
        strategy_routing_synchronizer: (
            RuntimeStrategyRoutingSynchronizer | None
        ) = None,
    ) -> None:
        self.cycle_runner = cycle_runner
        self.synchronizer = synchronizer
        self.strategy_routing_synchronizer = (
            strategy_routing_synchronizer
        )

    def run_cycle(self):
        self.synchronizer.synchronize()
        if self.strategy_routing_synchronizer is not None:
            self.strategy_routing_synchronizer.synchronize()
        return self.cycle_runner.run_cycle()


@dataclass(frozen=True, slots=True)
class PaperTradingProductionBundle:
    """本番Paper Tradingで生成した主要Component一式。"""

    settings: PaperTradingProductionSettings
    day_service: PaperTradingDayService
    trading_loop_component: TradingLoopComponent
    runtime_bundle: PaperTradingRuntimeBundle
    market_monitor: RealtimeMarketMonitor
    live_orchestrator: LiveTradingOrchestrator
    realtime_paper_trading_service: RealtimePaperTradingService
    signal_engine: RealtimeSignalEngine
    paper_broker: PaperBroker
    broker_recovery_result: PaperBrokerRecoveryResult
    portfolio_service: PortfolioService
    strategy_routing_snapshot: (
        StrategyRoutingSnapshot | None
    ) = None
    kabu_station_service: (
        KabuStationRealtimeService | None
    ) = None

    def run(self) -> PaperTradingDayResult:
        """Trading Loopを開始して終日運用を実行する。"""

        if self.kabu_station_service is not None:
            self.kabu_station_service.start(
                self.settings.codes
            )

        self.trading_loop_component.start()

        try:
            return self.day_service.run()
        finally:
            if self.trading_loop_component.is_running:
                self.trading_loop_component.stop()

            if self.kabu_station_service is not None:
                self.kabu_station_service.stop()


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
        market_calendar = TokyoMarketCalendar()

        completed_bar_provider = (
            KabuStationCompletedBarProvider()
        )
        kabu_client = KabuStationClient(
            settings=KabuStationClientSettings(
                api_password=(
                    settings.kabu_station_api_password
                    or ""
                ),
                base_url=settings.kabu_station_base_url,
                maximum_registered_symbols=50,
            )
        )
        kabu_provider = KabuStationRealtimeProvider(
            client=kabu_client
        )

        def websocket_factory(**kwargs):
            return KabuStationWebSocketClient(
                url=settings.kabu_station_websocket_url,
                **kwargs,
            )

        kabu_station_service = KabuStationRealtimeService(
            provider=kabu_provider,
            websocket_client_factory=websocket_factory,
            on_completed_bar=completed_bar_provider.accept,
            interval_minutes=5,
        )
        provide_five_minute_bars = completed_bar_provider
        market_data_source = "kabu-station-realtime"

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
            data_source=market_data_source,
            maximum_codes_per_poll=(
                settings.maximum_codes_per_poll
            ),
            rate_limit_cooldown_seconds=(
                settings.rate_limit_cooldown_seconds
            ),
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

        app_settings = Settings.from_environment(
            env_file=ROOT_DIR / ".env"
        )
        provisional_notifications = (
            NotificationComposition.create(
                settings=app_settings.notifications,
                require_channel=False,
            )
        )
        execution_observers = ()

        if provisional_notifications.channels:
            channel_names = (
                provisional_notifications.channel_names
            )
            notification_policy = NotificationRulePolicy(
                info_channels=channel_names,
                warning_channels=channel_names,
                error_channels=channel_names,
                critical_channels=channel_names,
                duplicate_cooldown_seconds=0,
            )
            notification_bundle = (
                NotificationComposition.create(
                    settings=app_settings.notifications,
                    policy=notification_policy,
                    require_channel=True,
                )
            )
            execution_observers = (
                ExecutionNotificationService(
                    gateway=notification_bundle.gateway,
                    signal_provider=signal_repository,
                ),
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
                execution_observers=(
                    execution_observers
                ),
                continue_on_notification_error=True,
            )
        )

        trace_recorder = (
            PaperTradingTraceRecorder(
                output_path=settings.risk_trace_path
            )
            if settings.risk_trace_enabled
            else None
        )

        if trace_recorder is not None:
            trace_recorder.runtime_started(
                market_data_mode=settings.market_data_mode,
                codes=settings.codes,
                database_path=settings.database_path,
            )

        risk_provider = PaperTradingPreTradeRiskProvider(
            broker=paper_broker,
            limits=PaperTradingRiskLimits(
                max_position_count=settings.max_position_count,
                max_position_value=settings.max_position_value,
                max_total_exposure=settings.max_total_exposure,
                minimum_cash_balance=settings.minimum_cash_balance,
                max_daily_loss=settings.max_daily_loss,
                max_daily_entries=settings.max_daily_entries,
            ),
        )
        risk_aware_execution_service = (
            RiskAwareQueueExecutionService(
                execution_service=queue_execution_service,
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

        end_of_day_liquidator = (
            EndOfDayLiquidationService(
                broker=paper_broker,
                order_queue_service=order_queue_service,
                execution_service=queue_execution_service,
                portfolio_update_service=portfolio_update_service,
                now_provider=resolved_now_provider,
            )
        )

        strategy_routing_snapshot = None
        symbol_strategy_router = None
        strategy_routing_repository = None

        if settings.strategy_routing_enabled:
            strategy_routing_repository = (
                DynamicWatchlistStrategyRoutingRepository(
                    report_path=(
                        settings.strategy_routing_report_path
                    ),
                    minimum_rating_tier=(
                        settings
                        .strategy_routing_minimum_rating_tier
                    ),
                    minimum_total_score=(
                        settings
                        .strategy_routing_minimum_total_score
                    ),
                    fallback_strategy_names=(
                        settings.enabled_strategy_names
                    ),
                    now_provider=resolved_now_provider,
                )
            )
            try:
                strategy_routing_snapshot = (
                    strategy_routing_repository.load()
                )
                symbol_strategy_router = SymbolStrategyRouter(
                    strategy_routing_snapshot
                )
            except DynamicWatchlistStrategyRoutingError:
                if not settings.strategy_routing_fail_open:
                    raise

        signal_engine = RealtimeSignalEngine(
            enabled_strategy_names=(
                settings.enabled_strategy_names
            ),
            high_breakout_candidate_provider=(
                RepositoryHighBreakoutCandidateProvider(
                    HighBreakoutCandidateRepository(
                        settings.database_path
                    )
                )
            ),
            symbol_strategy_router=symbol_strategy_router,
        )

        realtime_paper_trading_service = (
            RealtimePaperTradingService(
                signal_engine=signal_engine,
                order_queue_service=order_queue_service,
                queue_execution_service=(
                    queue_execution_service
                ),
                portfolio_update_service=(
                    portfolio_update_service
                ),
                market_price_updater=update_market_price,
                risk_aware_execution_service=(
                    risk_aware_execution_service
                ),
                risk_result_provider=risk_provider,
                risk_context_updater=risk_provider.prepare,
                require_risk_gate=True,
                trace_recorder=trace_recorder,
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

        runtime_watchlist_synchronizer = RuntimeWatchlistSynchronizer(
            watchlist_path=settings.watchlist_path,
            trading_loop_component=trading_loop_component,
            kabu_station_service=kabu_station_service,
            paper_broker=paper_broker,
            maximum_registered_symbols=50,
        )
        runtime_strategy_routing_synchronizer = None
        if strategy_routing_repository is not None:
            runtime_strategy_routing_synchronizer = (
                RuntimeStrategyRoutingSynchronizer(
                    repository=strategy_routing_repository,
                    signal_engine=signal_engine,
                    current_snapshot=strategy_routing_snapshot,
                    fail_open=settings.strategy_routing_fail_open,
                )
            )

        runtime_watchlist_cycle_runner = RuntimeWatchlistCycleRunner(
            cycle_runner=trading_loop_component,
            synchronizer=runtime_watchlist_synchronizer,
            strategy_routing_synchronizer=(
                runtime_strategy_routing_synchronizer
            ),
        )

        runtime_bundle = PaperTradingRuntimeFactory.create(
            database_path=settings.database_path,
            cycle_runner=runtime_watchlist_cycle_runner,
            portfolio_reader=portfolio_service,
            now_provider=resolved_now_provider,
        )

        watchlist_execution_integrity_hook = (
            WatchlistExecutionIntegrityPostRunHook(
                audit_service=WatchlistExecutionIntegrityService(
                    database_path=settings.database_path,
                    watchlist_path=settings.watchlist_path,
                    explainability_path=(
                        settings.watchlist_explainability_path
                    ),
                    trace_path=settings.risk_trace_path,
                ),
                report_path=(
                    settings
                    .watchlist_execution_integrity_report_path
                ),
            )
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
            end_of_day_liquidator=end_of_day_liquidator,
            post_run_hooks=(
                watchlist_execution_integrity_hook,
            ),
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
            live_orchestrator=live_orchestrator,
            realtime_paper_trading_service=(
                realtime_paper_trading_service
            ),
            signal_engine=signal_engine,
            paper_broker=paper_broker,
            broker_recovery_result=(
                broker_recovery_result
            ),
            portfolio_service=portfolio_service,
            strategy_routing_snapshot=(
                strategy_routing_snapshot
            ),
            kabu_station_service=kabu_station_service,
        )
