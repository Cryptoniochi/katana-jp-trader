"""Paper Trading本番経路のSignal-Risk-Broker Trace。"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.dynamic_watchlist.strategy_routing_models import (
    SymbolStrategyRoute,
)
from app.market.symbol_strategy_router import (
    StrategyRouteDecision,
)
from app.risk.paper_trading_pretrade_risk import (
    PaperTradingRiskDecision,
)
from app.trading.signal_models import TradeSignal


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaperTradingTraceEvent:
    """1件の追跡イベント。"""

    occurred_at: datetime
    event_type: str
    signal_id: str | None
    code: str | None
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "Trace日時にはタイムゾーンが必要です。"
            )
        if not self.event_type.strip():
            raise ValueError(
                "Traceイベント種別を指定してください。"
            )


@dataclass(frozen=True, slots=True)
class PaperTradingTraceSnapshot:
    """Trace集計。"""

    strategy_route_resolved_count: int
    routed_strategy_count: int
    fallback_strategy_count: int
    signal_generated_count: int
    risk_evaluated_count: int
    risk_allowed_count: int
    risk_blocked_count: int
    queue_enqueued_count: int
    broker_executed_count: int
    broker_skipped_count: int
    trace_error_count: int
    last_event: PaperTradingTraceEvent | None


class PaperTradingTraceRecorder:
    """JSON Linesとメモリへ本番経路を記録する。"""

    def __init__(
        self,
        *,
        output_path: Path | None = None,
    ) -> None:
        self.output_path = (
            None
            if output_path is None
            else Path(output_path).resolve()
        )
        self._lock = Lock()
        self._strategy_route_resolved_count = 0
        self._routed_strategy_count = 0
        self._fallback_strategy_count = 0
        self._signal_generated_count = 0
        self._risk_evaluated_count = 0
        self._risk_allowed_count = 0
        self._risk_blocked_count = 0
        self._queue_enqueued_count = 0
        self._broker_executed_count = 0
        self._broker_skipped_count = 0
        self._trace_error_count = 0
        self._last_event: PaperTradingTraceEvent | None = None

        if self.output_path is not None:
            self.output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            self.output_path.touch(exist_ok=True)

    def runtime_started(
        self,
        *,
        market_data_mode: str,
        codes: tuple[str, ...],
        database_path: Path,
    ) -> None:
        """Trace初期化とRuntime起動を記録する。"""

        self._record_event(
            PaperTradingTraceEvent(
                occurred_at=datetime.now(timezone.utc),
                event_type="runtime_started",
                signal_id=None,
                code=None,
                payload={
                    "market_data_mode": market_data_mode,
                    "code_count": len(codes),
                    "codes": list(codes),
                    "database_path": str(
                        Path(database_path).resolve()
                    ),
                    "trace_path": (
                        None
                        if self.output_path is None
                        else str(self.output_path)
                    ),
                },
            )
        )

    def runtime_stopped(
        self,
        *,
        reason: str,
    ) -> None:
        """Runtime停止を記録する。"""

        self._record_event(
            PaperTradingTraceEvent(
                occurred_at=datetime.now(timezone.utc),
                event_type="runtime_stopped",
                signal_id=None,
                code=None,
                payload={"reason": reason},
            )
        )


    def strategy_route_resolved(
        self,
        signal: TradeSignal,
        *,
        decision: StrategyRouteDecision,
        route: SymbolStrategyRoute | None,
    ) -> None:
        """シグナルに適用された銘柄別戦略ルートを記録する。"""

        self._record_signal_event(
            event_type="strategy_route_resolved",
            signal=signal,
            payload={
                "routed": decision.routed,
                "selected_strategy_names": list(
                    decision.strategy_names
                ),
                "reason": decision.reason,
                "route_source": (
                    "dynamic_watchlist"
                    if decision.routed
                    else "fallback"
                ),
                "rating_tier": (
                    route.rating_tier
                    if route is not None
                    else None
                ),
                "total_score": (
                    route.total_score
                    if route is not None
                    else None
                ),
                "strategy_score": (
                    route.strategy_score
                    if route is not None
                    else None
                ),
                "source_generated_at": (
                    route.source_generated_at.isoformat()
                    if (
                        route is not None
                        and route.source_generated_at is not None
                    )
                    else None
                ),
            },
        )

        with self._lock:
            self._strategy_route_resolved_count += 1

            if decision.routed:
                self._routed_strategy_count += 1
            else:
                self._fallback_strategy_count += 1

    def signal_generated(
        self,
        signal: TradeSignal,
        current_price: float,
    ) -> None:
        self._record_signal_event(
            event_type="signal_generated",
            signal=signal,
            payload={
                "action": signal.action.value,
                "quantity": signal.quantity,
                "signal_price": float(signal.signal_price),
                "current_price": float(current_price),
                "strategy_name": signal.strategy_name,
            },
        )
        with self._lock:
            self._signal_generated_count += 1

    def risk_evaluated(
        self,
        signal: TradeSignal,
        decision: PaperTradingRiskDecision,
    ) -> None:
        self._record_signal_event(
            event_type="risk_evaluated",
            signal=signal,
            payload={
                "allowed": decision.allows_new_entries,
                "blocked": decision.is_blocked,
                "reason": decision.reason,
                "daily_profit_loss": (
                    decision.daily_profit_loss
                ),
                "position_count": decision.position_count,
                "total_exposure": decision.total_exposure,
                "cash_balance": decision.cash_balance,
                "proposed_order_value": (
                    decision.proposed_order_value
                ),
                "daily_entry_count": (
                    decision.daily_entry_count
                ),
            },
        )
        with self._lock:
            self._risk_evaluated_count += 1
            if decision.is_blocked:
                self._risk_blocked_count += 1
            else:
                self._risk_allowed_count += 1

    def queue_enqueued(
        self,
        signal: TradeSignal,
        *,
        was_enqueued: bool,
    ) -> None:
        self._record_signal_event(
            event_type="queue_enqueued",
            signal=signal,
            payload={
                "was_enqueued": was_enqueued,
            },
        )
        if was_enqueued:
            with self._lock:
                self._queue_enqueued_count += 1

    def broker_result(
        self,
        signal: TradeSignal,
        *,
        executed: bool,
        saved_execution_count: int,
        blocked_reason: str | None = None,
    ) -> None:
        event_type = (
            "broker_executed"
            if executed
            else "broker_skipped"
        )
        self._record_signal_event(
            event_type=event_type,
            signal=signal,
            payload={
                "executed": executed,
                "saved_execution_count": (
                    saved_execution_count
                ),
                "blocked_reason": blocked_reason,
            },
        )
        with self._lock:
            if executed:
                self._broker_executed_count += 1
            else:
                self._broker_skipped_count += 1

    def snapshot(self) -> PaperTradingTraceSnapshot:
        with self._lock:
            return PaperTradingTraceSnapshot(
                strategy_route_resolved_count=(
                    self._strategy_route_resolved_count
                ),
                routed_strategy_count=(
                    self._routed_strategy_count
                ),
                fallback_strategy_count=(
                    self._fallback_strategy_count
                ),
                signal_generated_count=(
                    self._signal_generated_count
                ),
                risk_evaluated_count=(
                    self._risk_evaluated_count
                ),
                risk_allowed_count=self._risk_allowed_count,
                risk_blocked_count=self._risk_blocked_count,
                queue_enqueued_count=(
                    self._queue_enqueued_count
                ),
                broker_executed_count=(
                    self._broker_executed_count
                ),
                broker_skipped_count=(
                    self._broker_skipped_count
                ),
                trace_error_count=self._trace_error_count,
                last_event=self._last_event,
            )

    def _record_signal_event(
        self,
        *,
        event_type: str,
        signal: TradeSignal,
        payload: dict[str, Any],
    ) -> None:
        self._record_event(
            PaperTradingTraceEvent(
                occurred_at=datetime.now(timezone.utc),
                event_type=event_type,
                signal_id=signal.signal_id,
                code=signal.code,
                payload=payload,
            )
        )

    def _record_event(
        self,
        event: PaperTradingTraceEvent,
    ) -> None:
        with self._lock:
            self._last_event = event

        LOGGER.info(
            "paper-trading-trace "
            "event=%s signal_id=%s code=%s payload=%s",
            event.event_type,
            event.signal_id,
            event.code,
            json.dumps(
                event.payload,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

        if self.output_path is None:
            return

        try:
            serialized = {
                **asdict(event),
                "occurred_at": (
                    event.occurred_at.isoformat()
                ),
            }
            with self.output_path.open(
                "a",
                encoding="utf-8",
            ) as stream:
                stream.write(
                    json.dumps(
                        serialized,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
        except Exception:
            LOGGER.exception(
                "Paper Trading Traceの保存に失敗しました。"
            )
            with self._lock:
                self._trace_error_count += 1
