"""Fail-closed consistency check between broker executions and real positions.

The service compares a pre-submission real-account position baseline with the
latest kabu Station account state after broker execution reconciliation.  It is
read-only: it never submits, cancels, replaces, or retries an order.

A baseline is required because a filled BUY/SELL cannot be validated from the
post-trade position alone when the account already held the same symbol.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.live.live_account_state_service import LiveAccountState
from app.live.live_execution_reconciliation import (
    LiveExecutionReconciliation,
    LiveExecutionReconciliationState,
)
from app.trading.order_models import OrderSide, TradeOrder


class LiveExecutionPositionConsistencyDecision(StrEnum):
    CONSISTENT = "consistent"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LivePositionBaseline:
    code: str
    quantity: int

    def __post_init__(self) -> None:
        code = self.code.strip()
        if not code:
            raise ValueError("code is required")
        if self.quantity < 0:
            raise ValueError("baseline quantity must be non-negative")
        object.__setattr__(self, "code", code)


@dataclass(frozen=True, slots=True)
class LiveExecutionPositionConsistencyResult:
    decision: LiveExecutionPositionConsistencyDecision
    code: str
    baseline_quantity: int
    executed_quantity: int | None
    expected_quantity: int | None
    actual_quantity: int | None
    detail: str

    @property
    def may_proceed(self) -> bool:
        return self.decision is LiveExecutionPositionConsistencyDecision.CONSISTENT

    @property
    def may_retry_submission(self) -> bool:
        """A position check can never authorize resubmitting the same order."""
        return False


class _LiveAccountStateService(Protocol):
    def refresh(self) -> LiveAccountState: ...


class LiveExecutionPositionConsistencyService:
    """Validate broker execution quantity against authoritative real positions."""

    def __init__(self, *, account_state_service: _LiveAccountStateService) -> None:
        self.account_state_service = account_state_service

    def capture_baseline(self, order: TradeOrder) -> LivePositionBaseline:
        """Capture real position quantity immediately before submission."""
        state = self.account_state_service.refresh()
        return LivePositionBaseline(
            code=order.code,
            quantity=self._position_quantity(state, order.code),
        )

    def verify(
        self,
        *,
        order: TradeOrder,
        baseline: LivePositionBaseline,
        reconciliation: LiveExecutionReconciliation,
    ) -> LiveExecutionPositionConsistencyResult:
        if baseline.code != order.code:
            raise ValueError("baseline code does not match order code")

        if reconciliation.state is LiveExecutionReconciliationState.UNKNOWN:
            return self._unknown(
                order=order,
                baseline=baseline,
                detail="broker execution state is unknown; position consistency cannot be established",
            )

        executed_quantity = self._executed_quantity(reconciliation)
        if executed_quantity is None:
            return self._unknown(
                order=order,
                baseline=baseline,
                detail="broker cumulative execution quantity is invalid or unavailable",
            )
        if executed_quantity > order.quantity:
            return self._unknown(
                order=order,
                baseline=baseline,
                detail="broker cumulative execution exceeds KATANA order quantity",
            )

        expected = self._expected_quantity(
            side=order.side,
            baseline_quantity=baseline.quantity,
            executed_quantity=executed_quantity,
        )
        if expected is None:
            return self._unknown(
                order=order,
                baseline=baseline,
                detail="SELL execution exceeds the captured real-position baseline",
                executed_quantity=executed_quantity,
            )

        try:
            state = self.account_state_service.refresh()
        except Exception as exc:
            return LiveExecutionPositionConsistencyResult(
                decision=LiveExecutionPositionConsistencyDecision.UNKNOWN,
                code=order.code,
                baseline_quantity=baseline.quantity,
                executed_quantity=executed_quantity,
                expected_quantity=expected,
                actual_quantity=None,
                detail=f"real account position refresh failed: {type(exc).__name__}",
            )

        actual = self._position_quantity(state, order.code)
        if actual != expected:
            return LiveExecutionPositionConsistencyResult(
                decision=LiveExecutionPositionConsistencyDecision.MISMATCH,
                code=order.code,
                baseline_quantity=baseline.quantity,
                executed_quantity=executed_quantity,
                expected_quantity=expected,
                actual_quantity=actual,
                detail=(
                    "broker execution and real position disagree; fail closed and "
                    "perform read-only reconciliation again before any further action"
                ),
            )

        return LiveExecutionPositionConsistencyResult(
            decision=LiveExecutionPositionConsistencyDecision.CONSISTENT,
            code=order.code,
            baseline_quantity=baseline.quantity,
            executed_quantity=executed_quantity,
            expected_quantity=expected,
            actual_quantity=actual,
            detail="broker execution quantity is consistent with the real account position",
        )

    @staticmethod
    def _position_quantity(state: LiveAccountState, code: str) -> int:
        quantities = [position.quantity for position in state.positions if position.code == code]
        if not quantities:
            return 0
        return sum(quantities)

    @staticmethod
    def _executed_quantity(reconciliation: LiveExecutionReconciliation) -> int | None:
        value = reconciliation.cumulative_quantity
        if value is None or value < 0 or not float(value).is_integer():
            return None
        return int(value)

    @staticmethod
    def _expected_quantity(
        *,
        side: OrderSide,
        baseline_quantity: int,
        executed_quantity: int,
    ) -> int | None:
        if side is OrderSide.BUY:
            return baseline_quantity + executed_quantity
        expected = baseline_quantity - executed_quantity
        return expected if expected >= 0 else None

    @staticmethod
    def _unknown(
        *,
        order: TradeOrder,
        baseline: LivePositionBaseline,
        detail: str,
        executed_quantity: int | None = None,
    ) -> LiveExecutionPositionConsistencyResult:
        return LiveExecutionPositionConsistencyResult(
            decision=LiveExecutionPositionConsistencyDecision.UNKNOWN,
            code=order.code,
            baseline_quantity=baseline.quantity,
            executed_quantity=executed_quantity,
            expected_quantity=None,
            actual_quantity=None,
            detail=detail,
        )
