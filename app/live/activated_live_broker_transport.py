"""Phase 6-F activated kabu Station broker transport.

This module is deliberately separate from Phase 6-C LockedLiveBrokerTransport.
It can transmit only when all three independent gates are satisfied:
- construction-time explicit enable flag;
- runtime ARM;
- existing daily LiveArmingPolicy.

There is no retry. A transport exception is an ambiguous outcome and must be
persisted as UNKNOWN by the activated submission coordinator.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveArmingPolicy,
    LiveTradingLockError,
)
from app.live.kabu_station_cash_order_sender import KabuStationCashOrderSender
from app.live.live_broker_transport_models import LiveTransportRequest


NowProvider = Callable[[], datetime]


class ActivatedLiveTransportDecision(StrEnum):
    BLOCKED = "blocked"
    SUBMITTED = "submitted"


class ActivatedLiveTransportBlockReason(StrEnum):
    ACTIVATION_LOCK = "activation_lock"
    RUNTIME_LOCK = "runtime_lock"
    EXECUTION_MODE_LOCK = "execution_mode_lock"


@dataclass(frozen=True, slots=True)
class ActivatedLiveTransportResult:
    request: LiveTransportRequest
    decision: ActivatedLiveTransportDecision
    evaluated_at: datetime
    broker_order_id: str | None
    block_reason: ActivatedLiveTransportBlockReason | None
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
        if self.decision is ActivatedLiveTransportDecision.SUBMITTED:
            if not (self.broker_order_id or "").strip():
                raise ValueError("SUBMITTED requires broker_order_id.")
            if self.block_reason is not None:
                raise ValueError("SUBMITTED cannot have block_reason.")
        else:
            if self.broker_order_id is not None:
                raise ValueError("BLOCKED cannot have broker_order_id.")
            if self.block_reason is None:
                raise ValueError("BLOCKED requires block_reason.")


class ActivatedKabuStationLiveTransport:
    """Explicitly activated, non-retrying kabu Station order transport."""

    def __init__(
        self,
        *,
        sender: KabuStationCashOrderSender,
        execution_settings: ExecutionModeSettings,
        activation_enabled: bool = False,
        runtime_armed: bool = False,
        arming_policy: LiveArmingPolicy | None = None,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.sender = sender
        self.execution_settings = execution_settings
        self.activation_enabled = bool(activation_enabled)
        self.runtime_armed = bool(runtime_armed)
        self.arming_policy = arming_policy or LiveArmingPolicy()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def submit(
        self,
        request: LiveTransportRequest,
        *,
        trading_date: date,
    ) -> ActivatedLiveTransportResult:
        evaluated_at = self._current_time()

        if not self.activation_enabled:
            return self._blocked(
                request,
                ActivatedLiveTransportBlockReason.ACTIVATION_LOCK,
                evaluated_at,
                "Activated live transport is disabled.",
            )

        if not self.runtime_armed:
            return self._blocked(
                request,
                ActivatedLiveTransportBlockReason.RUNTIME_LOCK,
                evaluated_at,
                "Activated live transport runtime ARM is disabled.",
            )

        try:
            self.arming_policy.require_authorized(
                self.execution_settings,
                trading_date=trading_date,
            )
        except LiveTradingLockError as error:
            return self._blocked(
                request,
                ActivatedLiveTransportBlockReason.EXECUTION_MODE_LOCK,
                evaluated_at,
                f"Execution mode authorization rejected: {error}",
            )

        # Exactly one network submission attempt. Never retry here.
        broker_order_id = self.sender.send_once(request.order)
        return ActivatedLiveTransportResult(
            request=request,
            decision=ActivatedLiveTransportDecision.SUBMITTED,
            evaluated_at=self._current_time(),
            broker_order_id=broker_order_id,
            block_reason=None,
            message="kabu Station confirmed the live order with OrderId.",
        )

    @staticmethod
    def _blocked(request, reason, evaluated_at, message):
        return ActivatedLiveTransportResult(
            request=request,
            decision=ActivatedLiveTransportDecision.BLOCKED,
            evaluated_at=evaluated_at,
            broker_order_id=None,
            block_reason=reason,
            message=message,
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
