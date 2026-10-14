"""Persist Live protective stops only from broker-confirmed BUY fills."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
    LiveExecutionTrackingResult,
)
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopRecord,
    SQLiteLiveProtectiveStopRepository,
)
from app.trading.order_models import OrderSide, TradeOrder


class LiveConfirmedEntryStopDecision(StrEnum):
    RECORDED = "recorded"
    NO_CONFIRMED_FILL = "no_confirmed_fill"
    NOT_BUY = "not_buy"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveConfirmedEntryStopResult:
    decision: LiveConfirmedEntryStopDecision
    record: LiveProtectiveStopRecord | None
    detail: str


class LiveConfirmedEntryStopRecorder:
    """Convert authoritative reconciliation fill details into durable stop state.

    Broker cumulative quantity alone is insufficient: every persisted stop
    requires positive RecType=8 fill details whose quantities exactly equal the
    broker cumulative quantity, plus a consistent authoritative position check.
    """

    _CONSISTENT_FILL_DECISIONS = {
        LiveExecutionTrackingDecision.PARTIALLY_FILLED_CONSISTENT,
        LiveExecutionTrackingDecision.FILLED_CONSISTENT,
        LiveExecutionTrackingDecision.TERMINATED_CONSISTENT,
    }

    def __init__(
        self,
        *,
        repository: SQLiteLiveProtectiveStopRepository,
        stop_loss_rate: float = 0.01,
    ) -> None:
        if not 0 < stop_loss_rate < 1:
            raise ValueError("stop_loss_rate must be between zero and one")
        self.repository = repository
        self.stop_loss_rate = float(stop_loss_rate)

    def record(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date: date,
        tracking_result: LiveExecutionTrackingResult,
    ) -> LiveConfirmedEntryStopResult:
        if order.side is not OrderSide.BUY:
            return LiveConfirmedEntryStopResult(
                LiveConfirmedEntryStopDecision.NOT_BUY,
                None,
                "Protective entry stops are created from BUY executions only.",
            )
        if tracking_result.execution_key != execution_key:
            return self._blocked("Tracking result execution key does not match.")
        if (
            tracking_result.decision not in self._CONSISTENT_FILL_DECISIONS
            or not tracking_result.position_confirmed
            or tracking_result.lifecycle is None
        ):
            return LiveConfirmedEntryStopResult(
                LiveConfirmedEntryStopDecision.NO_CONFIRMED_FILL,
                None,
                "No broker fill with authoritative position consistency is confirmed.",
            )

        reconciliation = tracking_result.lifecycle.reconciliation
        cumulative = reconciliation.cumulative_quantity
        fills = reconciliation.fills
        if cumulative is None or cumulative <= 0 or not fills:
            return self._blocked(
                "Broker cumulative execution lacks exact positive fill details."
            )
        rounded = round(cumulative)
        if abs(cumulative - rounded) > 1e-9:
            return self._blocked("Broker cumulative quantity is not integral.")
        quantity = int(rounded)
        if quantity > order.quantity:
            return self._blocked("Broker cumulative quantity exceeds entry order quantity.")

        fill_quantity = sum(fill.quantity for fill in fills)
        if abs(fill_quantity - cumulative) > 1e-9:
            return self._blocked(
                "Broker fill-detail quantity does not equal cumulative execution."
            )
        if any(fill.price <= 0 or fill.quantity <= 0 for fill in fills):
            return self._blocked("Broker fill details contain non-positive values.")

        average = sum(fill.quantity * fill.price for fill in fills) / fill_quantity
        record = self.repository.synchronize_confirmed_entry_fill(
            code=order.code,
            entry_execution_key=execution_key,
            trading_date=trading_date,
            cumulative_quantity=quantity,
            average_fill_price=average,
            stop_loss_rate=self.stop_loss_rate,
        )
        return LiveConfirmedEntryStopResult(
            LiveConfirmedEntryStopDecision.RECORDED,
            record,
            "Durable protective stop synchronized from confirmed broker fills.",
        )

    @staticmethod
    def _blocked(detail: str) -> LiveConfirmedEntryStopResult:
        return LiveConfirmedEntryStopResult(
            LiveConfirmedEntryStopDecision.BLOCKED, None, detail
        )
