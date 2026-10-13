"""Read-only reconciliation of submitted live orders against kabu Station.

The service deliberately does not submit, cancel, or retry orders.  A successful
``/sendorder`` response only proves broker acceptance; execution is established
from the broker's order list by matching the returned broker OrderId.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class LiveExecutionReconciliationState(StrEnum):
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    TERMINATED_UNFILLED = "terminated_unfilled"
    TERMINATED_PARTIAL = "terminated_partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveExecutionFill:
    execution_id: str | None
    quantity: float
    price: float


@dataclass(frozen=True, slots=True)
class LiveExecutionReconciliation:
    broker_order_id: str
    state: LiveExecutionReconciliationState
    order_quantity: float | None
    cumulative_quantity: float | None
    remaining_quantity: float | None
    fills: tuple[LiveExecutionFill, ...]
    detail: str

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            LiveExecutionReconciliationState.FILLED,
            LiveExecutionReconciliationState.TERMINATED_UNFILLED,
            LiveExecutionReconciliationState.TERMINATED_PARTIAL,
        }

    @property
    def may_retry_submission(self) -> bool:
        """Reconciliation never authorizes resubmitting the same order."""
        return False


class _OrdersClient(Protocol):
    def orders(self, *, product: int = 0) -> tuple[dict[str, Any], ...]: ...


class LiveExecutionReconciliationService:
    """Reconcile one broker OrderId without causing broker-side mutations."""

    _TERMINAL_ORDER_STATE = 5

    def __init__(self, *, client: _OrdersClient, product: int = 1) -> None:
        if product not in {0, 1, 2, 3, 4}:
            raise ValueError("product must be between 0 and 4")
        self.client = client
        self.product = product

    def reconcile(self, broker_order_id: str) -> LiveExecutionReconciliation:
        order_id = str(broker_order_id or "").strip()
        if not order_id:
            raise ValueError("broker_order_id is required")

        try:
            orders = self.client.orders(product=self.product)
        except Exception as exc:  # fail closed: never turn read failure into retry permission
            return self._unknown(order_id, f"orders read failed: {type(exc).__name__}")

        matches = [item for item in orders if str(item.get("ID") or "").strip() == order_id]
        if len(matches) != 1:
            reason = "broker order not found" if not matches else "duplicate broker OrderId"
            return self._unknown(order_id, reason)

        order = matches[0]
        order_qty = self._number(order.get("OrderQty"))
        cum_qty = self._number(order.get("CumQty"))
        order_state = self._integer(order.get("OrderState"))
        if order_qty is None or order_qty <= 0 or cum_qty is None or cum_qty < 0:
            return self._unknown(order_id, "invalid broker quantities")
        if cum_qty > order_qty:
            return self._unknown(order_id, "cumulative quantity exceeds order quantity")
        if order_state is None:
            return self._unknown(order_id, "missing OrderState")

        fills = self._fills(order)
        remaining = order_qty - cum_qty
        if cum_qty == order_qty:
            state = LiveExecutionReconciliationState.FILLED
            detail = "broker reports full cumulative execution"
        elif order_state == self._TERMINAL_ORDER_STATE:
            if cum_qty == 0:
                state = LiveExecutionReconciliationState.TERMINATED_UNFILLED
                detail = "broker order is terminal with no execution"
            else:
                state = LiveExecutionReconciliationState.TERMINATED_PARTIAL
                detail = "broker order is terminal after partial execution"
        elif cum_qty > 0:
            state = LiveExecutionReconciliationState.PARTIALLY_FILLED
            detail = "broker reports partial cumulative execution"
        else:
            state = LiveExecutionReconciliationState.ACCEPTED
            detail = "broker order exists and has no execution yet"

        return LiveExecutionReconciliation(
            broker_order_id=order_id,
            state=state,
            order_quantity=order_qty,
            cumulative_quantity=cum_qty,
            remaining_quantity=remaining,
            fills=fills,
            detail=detail,
        )

    @staticmethod
    def _fills(order: dict[str, Any]) -> tuple[LiveExecutionFill, ...]:
        result: list[LiveExecutionFill] = []
        details = order.get("Details")
        if not isinstance(details, list):
            return ()
        for item in details:
            if not isinstance(item, dict) or LiveExecutionReconciliationService._integer(item.get("RecType")) != 8:
                continue
            qty = LiveExecutionReconciliationService._number(item.get("Qty"))
            price = LiveExecutionReconciliationService._number(item.get("Price"))
            if qty is None or qty <= 0 or price is None or price < 0:
                continue
            execution_id = str(item.get("ExecutionID") or "").strip() or None
            result.append(LiveExecutionFill(execution_id=execution_id, quantity=qty, price=price))
        return tuple(result)

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number else None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _unknown(order_id: str, detail: str) -> LiveExecutionReconciliation:
        return LiveExecutionReconciliation(
            broker_order_id=order_id,
            state=LiveExecutionReconciliationState.UNKNOWN,
            order_quantity=None,
            cumulative_quantity=None,
            remaining_quantity=None,
            fills=(),
            detail=detail,
        )
