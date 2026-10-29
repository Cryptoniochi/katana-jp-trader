"""Concrete Paper-free production composition for activated Live trading."""
from __future__ import annotations

import time
from datetime import datetime, time as datetime_time, timezone
from threading import Event
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.bar_repository import MarketBarRepository
from app.market.high_breakout_candidate_provider import (
    RepositoryHighBreakoutCandidateProvider,
)
from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateRepository,
)
from app.database import initialize_database
from app.live.final_live_runtime_composition import FinalLiveRuntimeFactory
from app.live.kabu_station_cash_order_sender import (
    KabuStationCashOrderSender,
    KabuStationCashOrderSettings,
)
from app.live.live_production_application import LiveProductionApplicationFactory
from app.live.live_runtime_kill_switch_composition import (
    LiveRuntimeKillSwitchComposition,
)
from app.live.live_runtime_read_only_composition import (
    LiveRuntimeReadOnlyProviderFactory,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.live_signal_execution_bridge import LiveRealtimeSignalIntentProvider
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits
from app.market.kabu_station_client import KabuStationClient, KabuStationClientSettings
from app.market.kabu_station_completed_bar_provider import KabuStationCompletedBarProvider
from app.market.kabu_station_realtime_provider import KabuStationRealtimeProvider
from app.market.kabu_station_realtime_service import KabuStationRealtimeService
from app.market.kabu_station_websocket import KabuStationWebSocketClient
from app.market.models import StockPrice
from app.market.realtime_signal_engine import RealtimeSignalEngine
from app.dynamic_watchlist.strategy_routing_repository import (
    DynamicWatchlistStrategyRoutingError,
    DynamicWatchlistStrategyRoutingRepository,
)
from app.market.symbol_strategy_router import SymbolStrategyRouter
from app.runtime.daily_report_service import SQLiteDailyTradeRepository
from app.runtime.paper_trading_composition import PaperTradingProductionSettings
from app.runtime.session_service import RuntimeSessionService

TOKYO=ZoneInfo("Asia/Tokyo")


class LiveProductionCompositionError(RuntimeError):
    pass


class _LatestPriceBuffer:
    """Latest PUSH prices plus a startup-ready signal.

    A Live cycle must not run before at least one valid kabu Station PUSH tick
    has reached this process.  Per-symbol price lookup remains fail-closed:
    receiving one symbol never makes another symbol's price available.
    """

    def __init__(self):
        self._prices: dict[str, float] = {}
        self._first_price_received = Event()

    def accept(self, tick):
        code = str(tick.code).strip()
        price = float(tick.price)
        if not code or price <= 0:
            return
        self._prices[code] = price
        self._first_price_received.set()

    def has_received_price(self) -> bool:
        return self._first_price_received.is_set()

    def price(self, code: str) -> float:
        try:
            return self._prices[code.strip()]
        except KeyError as error:
            raise LiveProductionCompositionError(
                f"No realtime tick price is available for {code}."
            ) from error


class ConcreteLiveProductionApplication:
    """Own realtime market data and drive the Live application every 30 seconds."""

    def __init__(self,*,application,market_service,session_service,
                 trading_date,cycle_interval_seconds,eod_liquidation_flow,
                 registration_codes,
                 realtime_price_ready_provider=None,
                 now_provider=None,sleeper=None):
        self.application=application
        self.market_service=market_service
        self.session_service=session_service
        self.trading_date=trading_date
        self.cycle_interval_seconds=float(cycle_interval_seconds)
        self.eod_liquidation_flow=eod_liquidation_flow
        self.registration_codes=tuple(registration_codes)
        self.realtime_price_ready_provider=(
            realtime_price_ready_provider
            if realtime_price_ready_provider is not None
            else lambda: True
        )
        self.now_provider=now_provider or (lambda: datetime.now(timezone.utc))
        self.sleeper=sleeper or time.sleep

    def run(self)->int:
        market_open=datetime.strptime("09:00","%H:%M").time()
        lunch_start=datetime.strptime("11:30","%H:%M").time()
        lunch_end=datetime.strptime("12:30","%H:%M").time()
        market_close=datetime.strptime("15:25","%H:%M").time()
        stop_at=datetime.strptime("15:30","%H:%M").time()

        self.session_service.start()
        try:
            self.market_service.start(self.registration_codes)
            while True:
                now=self.now_provider()
                if now.tzinfo is None:
                    raise ValueError("now_provider must return timezone-aware datetime.")
                local=now.astimezone(TOKYO)
                local_time=local.time().replace(tzinfo=None)
                if local.date()!=self.trading_date or local_time>=market_close:
                    break

                # The scheduled service starts at 08:45. Keep market data and
                # heartbeat alive, but never evaluate or submit entries before
                # the Tokyo cash session opens at 09:00.
                self.session_service.record_heartbeat()
                if local_time < market_open:
                    self.sleeper(self.cycle_interval_seconds)
                    continue

                # Lunch: keep heartbeat alive, but do not generate/submit entries.
                if lunch_start <= local_time < lunch_end:
                    self.sleeper(self.cycle_interval_seconds)
                    continue

                # Do not evaluate strategies until this Live process has actually
                # received at least one valid realtime PUSH price.  start() only
                # starts the WebSocket thread; it does not guarantee that the first
                # PUSH message has arrived before this loop begins.
                #
                # Keep heartbeat alive while warming up.  Per-symbol lookup remains
                # fail-closed later at the final order boundary, so one received
                # symbol can never be used as another symbol's price.
                if not self.realtime_price_ready_provider():
                    self.sleeper(min(self.cycle_interval_seconds, 1.0))
                    continue

                # Prime runtime health before the first eligible Live cycle and
                # after an intentional no-cycle interval (pre-open/lunch).
                #
                # The Kill Switch evaluates runtime health inside run_cycle().
                # RuntimeHealthMonitorService requires both a fresh heartbeat
                # and a fresh cycle.  Without this bootstrap record, the first
                # real cycle can never pass its own precondition; after lunch,
                # the deliberately old last_cycle_at creates the same deadlock.
                #
                # This records runtime liveness only.  It does not evaluate a
                # strategy, create an execution, or transmit an order.
                session_snapshot=self.session_service.snapshot()
                last_cycle_at=session_snapshot.last_cycle_at
                cycle_stale=(
                    last_cycle_at is None
                    or (now.astimezone(timezone.utc)
                        - last_cycle_at.astimezone(timezone.utc)).total_seconds()
                    >= 180.0
                )
                if cycle_stale:
                    self.session_service.record_cycle(successful=True)

                result=self.application.run_cycle(trading_date=self.trading_date)
                self.session_service.record_cycle(
                    successful=(getattr(result.decision,"value","")!="blocked")
                )
                self.sleeper(self.cycle_interval_seconds)

            # From 15:25 through 15:30, repeatedly perform authoritative EOD
            # verification.  A still-working SELL is left untouched by the EOD
            # conflict resolver; retries therefore poll for flatness without
            # cancel/replace churn or duplicate submission.
            while True:
                result=self.eod_liquidation_flow.submit_all(
                    trading_date=self.trading_date
                )
                decision=getattr(getattr(result,"decision",None),"value","")
                if decision=="complete":
                    return 0

                now=self.now_provider()
                if now.tzinfo is None:
                    raise ValueError("now_provider must return timezone-aware datetime.")
                local=now.astimezone(TOKYO)
                local_time=local.time().replace(tzinfo=None)
                if local.date()!=self.trading_date or local_time>=stop_at:
                    return 1
                self.session_service.record_heartbeat()
                self.sleeper(self.cycle_interval_seconds)
        finally:
            try:
                self.market_service.stop()
            finally:
                try:
                    self.session_service.stop()
                except Exception:
                    pass


class ConcreteLiveProductionFactory:
    """Build the complete Live graph without constructing PaperBroker."""

    @staticmethod
    def create(*,production_settings:PaperTradingProductionSettings,
               execution_settings,trading_date,environment,
               production_activation_enabled:bool=False,
               runtime_armed:bool=False,
               now_provider=None,sleeper=None):
        now=now_provider or (lambda: datetime.now(timezone.utc))
        db=Path(production_settings.database_path)
        db.parent.mkdir(parents=True, exist_ok=True)
        initialize_database(db)

        client=KabuStationClient(settings=KabuStationClientSettings(
            api_password=production_settings.kabu_station_api_password or "",
            base_url=production_settings.kabu_station_base_url,
            maximum_registered_symbols=50,
        ))
        provider=KabuStationRealtimeProvider(client=client)
        bars=KabuStationCompletedBarProvider()
        bar_repository=MarketBarRepository(db)
        day_start=datetime.combine(
            trading_date, datetime_time.min, tzinfo=TOKYO
        )
        day_end=datetime.combine(
            trading_date, datetime_time.max, tzinfo=TOKYO
        )
        for code in production_settings.codes:
            bars.seed(
                bar_repository.read(
                    code,
                    interval_minutes=5,
                    start_at=day_start,
                    end_at=day_end,
                )
            )

        def accept_completed_bar(bar) -> None:
            stock_price=StockPrice(
                code=bar.code,
                datetime=bar.started_at,
                open=bar.open_price,
                high=bar.high_price,
                low=bar.low_price,
                close=bar.close_price,
                volume=max(0, int(round(bar.volume))),
            )
            bars.accept_stock_price(stock_price)
            bar_repository.save_all(
                [stock_price],
                interval_minutes=5,
                data_source="kabu_station_realtime",
            )

        prices=_LatestPriceBuffer()
        market_service=KabuStationRealtimeService(
            provider=provider,
            websocket_client_factory=lambda **kwargs: KabuStationWebSocketClient(
                url=production_settings.kabu_station_websocket_url, **kwargs),
            on_completed_bar=accept_completed_bar,
            on_tick=prices.accept,
            interval_minutes=5,
        )

        routing=None
        if production_settings.strategy_routing_enabled:
            repo=DynamicWatchlistStrategyRoutingRepository(
                report_path=production_settings.strategy_routing_report_path,
                minimum_rating_tier=production_settings.strategy_routing_minimum_rating_tier,
                minimum_total_score=production_settings.strategy_routing_minimum_total_score,
                fallback_strategy_names=production_settings.enabled_strategy_names,
                now_provider=now,
            )
            try:
                routing=SymbolStrategyRouter(repo.load())
            except DynamicWatchlistStrategyRoutingError:
                if not production_settings.strategy_routing_fail_open:
                    raise

        signal_engine=RealtimeSignalEngine(
            enabled_strategy_names=production_settings.enabled_strategy_names,
            high_breakout_candidate_provider=RepositoryHighBreakoutCandidateProvider(
                HighBreakoutCandidateRepository(db)),
            symbol_strategy_router=routing,
        )
        intent_provider=LiveRealtimeSignalIntentProvider(
            signal_engine=signal_engine,
            price_provider=lambda: tuple(
                bar for code in production_settings.codes
                for bar in bars(code,trading_date)
            ),
        )

        session=RuntimeSessionService(now_provider=now)
        daily=SQLiteDailyTradeRepository(db)
        readonly=LiveRuntimeReadOnlyProviderFactory.create(
            daily_trade_repository=daily,
            runtime_session_service=session,
            kabu_station_report_path=production_settings.live_read_only_report_path,
            three_way_reconciliation_report_path=production_settings.three_way_reconciliation_report_path,
            fault_tolerance_state_path=production_settings.fault_tolerance_state_path,
            manual_kill_switch_state_path=production_settings.manual_kill_switch_state_path,
            now_provider=now,
        )
        # Production Live safety must be based on a fresh authoritative broker
        # read, not the legacy Phase 5B Paper/Shadow/flat-account reconciliation.
        # The account service is owned by FinalLiveRuntimeFactory, so the closure
        # is bound immediately after that graph is constructed.  Any call before
        # binding, broker-read failure, or fault-tolerance read failure fails closed.
        safety_account_service = {"value": None}

        def safety() -> LiveOrderSafetySnapshot:
            evaluated_at=now()
            if evaluated_at.tzinfo is None:
                raise ValueError("now_provider must return timezone-aware datetime.")
            evaluated_at=evaluated_at.astimezone(timezone.utc)
            service=safety_account_service["value"]
            if service is None:
                return LiveOrderSafetySnapshot(
                    safe_stop_active=True,
                    reconciliation_consistent=False,
                    reconciliation_state="broker_safety_unbound",
                    evaluated_at=evaluated_at,
                )
            try:
                service.refresh()
            except Exception as error:
                return LiveOrderSafetySnapshot(
                    safe_stop_active=True,
                    reconciliation_consistent=False,
                    reconciliation_state=(
                        "broker_state_unavailable:"
                        f"{type(error).__name__}:{error}"
                    ),
                    evaluated_at=evaluated_at,
                )
            try:
                attempt=readonly.fault_tolerance_attempt_provider()
            except Exception:
                return LiveOrderSafetySnapshot(
                    safe_stop_active=True,
                    reconciliation_consistent=False,
                    reconciliation_state="fault_tolerance_unavailable",
                    evaluated_at=evaluated_at,
                )

            # A successful refresh above is the authoritative Production Live
            # reconciliation result. Do not pass it through the legacy Phase 5B
            # Paper/Shadow reconciliation state vocabulary.
            safe_stop_active = (
                attempt is not None
                and getattr(getattr(attempt, "decision", None), "value", None)
                == "safe_stop"
            )
            return LiveOrderSafetySnapshot(
                safe_stop_active=safe_stop_active,
                reconciliation_consistent=True,
                reconciliation_state="broker_state_fresh",
                evaluated_at=evaluated_at,
            )
        kill=LiveRuntimeKillSwitchComposition(
            daily_profit_loss_provider=readonly.daily_profit_loss_provider,
            consecutive_loss_count_provider=readonly.consecutive_loss_count_provider,
            runtime_health_ok_provider=readonly.runtime_health_ok_provider,
            heartbeat_alive_provider=readonly.heartbeat_alive_provider,
            broker_available_provider=readonly.broker_available_provider,
            manual_blocked_provider=readonly.manual_blocked_provider,
            max_daily_loss=production_settings.max_daily_loss,
            now_provider=now,
        )

        def required_int(name:str)->int:
            raw=str(environment.get(name,"")).strip()
            if not raw:
                raise LiveProductionCompositionError(f"{name} must be explicitly configured.")
            try: return int(raw)
            except ValueError as error:
                raise LiveProductionCompositionError(f"{name} must be an integer.") from error
        fund=str(environment.get("KATANA_LIVE_CASH_BUY_FUND_TYPE","")).strip().upper()
        if not fund:
            raise LiveProductionCompositionError(
                "KATANA_LIVE_CASH_BUY_FUND_TYPE must be explicitly configured."
            )
        sender=KabuStationCashOrderSender(
            client=client,
            settings=KabuStationCashOrderSettings(
                exchange=required_int("KATANA_LIVE_EXCHANGE"),
                account_type=required_int("KATANA_LIVE_ACCOUNT_TYPE"),
                cash_buy_fund_type=fund,
            ),
        )
        risk=LiveRiskManager(limits=RiskLimits(
            max_position_count=production_settings.max_position_count,
            max_position_value=production_settings.max_position_value,
            max_total_exposure=production_settings.max_total_exposure,
            minimum_cash_balance=production_settings.minimum_cash_balance,
            max_daily_loss=production_settings.max_daily_loss,
        ))
        final=FinalLiveRuntimeFactory.create(
            database_path=db,kabu_client=client,sender=sender,
            execution_settings=execution_settings,daily_trade_repository=daily,
            kabu_station_report_path=production_settings.live_read_only_report_path,
            live_equity_peak_path=production_settings.live_read_only_report_path.with_name("live_equity_peak.json"),
            risk_manager=risk,safety_snapshot_provider=safety,
            kill_switch_snapshot_provider=kill,market_price_provider=prices.price,
            activation_enabled=production_activation_enabled,
            runtime_armed=runtime_armed,now_provider=now,
        )
        safety_account_service["value"]=final.account.account_state_service

        # Refresh real account before PUSH registration so held symbols remain
        # protected even when today's watchlist changed.
        state=final.account.account_state_service.refresh()
        codes=tuple(dict.fromkeys(
            (*production_settings.codes, *(p.code for p in state.positions))
        ))
        if len(codes)>50:
            raise LiveProductionCompositionError(
                "Watchlist plus actual Live positions exceeds kabu Station 50-symbol limit."
            )
        # The provider is stateful by design: one engine evaluation produces
        # both BUY intents and last_exit_signals. The application consumes exits
        # before permitting any new BUY in that same cycle.
        application=LiveProductionApplicationFactory.create(
            execution_settings=execution_settings,final_runtime=final,
            entry_intent_provider=intent_provider)
        return ConcreteLiveProductionApplication(
            application=application,market_service=market_service,
            session_service=session,trading_date=trading_date,
            cycle_interval_seconds=production_settings.cycle_interval_seconds,
            eod_liquidation_flow=final.eod_liquidation_flow,
            registration_codes=codes,
            realtime_price_ready_provider=prices.has_received_price,
            now_provider=now,sleeper=sleeper)
