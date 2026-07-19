"""Position Sizingの判定と承認数量計算を行う。"""

from __future__ import annotations

from math import floor, isfinite

from app.risk.position_sizing_models import (
    PositionSizingPolicy,
    PositionSizingReason,
    PositionSizingRequest,
    PositionSizingResult,
    PositionSizingStatus,
)


class PositionSizingService:
    """複数のリスク制約から注文可能数量を決定する。"""

    def __init__(
        self,
        *,
        policy: PositionSizingPolicy,
    ) -> None:
        """Position Sizing Policyを設定する。"""

        self.policy = policy

    def calculate(
        self,
        request: PositionSizingRequest,
    ) -> PositionSizingResult:
        """希望数量を各制約へ適用して承認数量を返す。"""

        if not isfinite(request.price) or request.price <= 0:
            return self._reject(
                request=request,
                reason=PositionSizingReason.INVALID_PRICE,
            )

        if (
            request.opens_new_position
            and request.current_position_count
            >= self.policy.max_position_count
        ):
            return self._reject(
                request=request,
                reason=(
                    PositionSizingReason.MAX_POSITION_COUNT_REACHED
                ),
                limiting_value=float(
                    self.policy.max_position_count
                ),
            )

        requested_lot_quantity = self._round_down_to_lot(
            request.requested_quantity
        )

        if requested_lot_quantity < self.policy.lot_size:
            return self._reject(
                request=request,
                reason=PositionSizingReason.BELOW_MINIMUM_LOT,
                limiting_value=float(self.policy.lot_size),
            )

        current_position_value = (
            request.current_position_quantity
            * request.price
        )
        available_position_value = max(
            0.0,
            self.policy.max_position_value
            - current_position_value,
        )
        available_portfolio_value = max(
            0.0,
            self.policy.max_portfolio_exposure
            - request.current_portfolio_exposure,
        )

        capacity_by_position = self._quantity_for_value(
            available_position_value,
            request.price,
        )
        capacity_by_order = self._quantity_for_value(
            self.policy.max_order_value,
            request.price,
        )
        capacity_by_portfolio = self._quantity_for_value(
            available_portfolio_value,
            request.price,
        )
        capacity_by_buying_power = self._quantity_for_value(
            request.buying_power,
            request.price,
        )

        capacities = (
            (
                PositionSizingReason.REDUCED_TO_LOT_SIZE,
                requested_lot_quantity,
                float(requested_lot_quantity),
            ),
            (
                PositionSizingReason.REDUCED_BY_POSITION_LIMIT,
                capacity_by_position,
                available_position_value,
            ),
            (
                PositionSizingReason.REDUCED_BY_ORDER_LIMIT,
                capacity_by_order,
                self.policy.max_order_value,
            ),
            (
                PositionSizingReason.REDUCED_BY_PORTFOLIO_LIMIT,
                capacity_by_portfolio,
                available_portfolio_value,
            ),
            (
                PositionSizingReason.REDUCED_BY_BUYING_POWER,
                capacity_by_buying_power,
                request.buying_power,
            ),
        )

        limiting_reason, approved_quantity, limiting_value = min(
            capacities,
            key=lambda item: item[1],
        )

        if approved_quantity < self.policy.lot_size:
            return self._reject_for_capacity(
                request=request,
                capacity_by_position=capacity_by_position,
                capacity_by_order=capacity_by_order,
                capacity_by_portfolio=capacity_by_portfolio,
                capacity_by_buying_power=capacity_by_buying_power,
            )

        approved_order_value = (
            approved_quantity * request.price
        )

        if approved_quantity == request.requested_quantity:
            return PositionSizingResult(
                code=request.code,
                status=PositionSizingStatus.APPROVED,
                reason=PositionSizingReason.WITHIN_LIMITS,
                requested_quantity=request.requested_quantity,
                approved_quantity=approved_quantity,
                price=request.price,
                approved_order_value=approved_order_value,
                limiting_value=None,
            )

        return PositionSizingResult(
            code=request.code,
            status=PositionSizingStatus.REDUCED,
            reason=limiting_reason,
            requested_quantity=request.requested_quantity,
            approved_quantity=approved_quantity,
            price=request.price,
            approved_order_value=approved_order_value,
            limiting_value=limiting_value,
        )

    def _reject_for_capacity(
        self,
        *,
        request: PositionSizingRequest,
        capacity_by_position: int,
        capacity_by_order: int,
        capacity_by_portfolio: int,
        capacity_by_buying_power: int,
    ) -> PositionSizingResult:
        """0または最低売買単位未満となった主因を判定する。"""

        if capacity_by_buying_power < self.policy.lot_size:
            return self._reject(
                request=request,
                reason=(
                    PositionSizingReason.INSUFFICIENT_BUYING_POWER
                ),
                limiting_value=request.buying_power,
            )

        if capacity_by_position < self.policy.lot_size:
            return self._reject(
                request=request,
                reason=PositionSizingReason.NO_AVAILABLE_CAPACITY,
                limiting_value=(
                    self.policy.max_position_value
                ),
            )

        if capacity_by_order < self.policy.lot_size:
            return self._reject(
                request=request,
                reason=PositionSizingReason.BELOW_MINIMUM_LOT,
                limiting_value=self.policy.max_order_value,
            )

        if capacity_by_portfolio < self.policy.lot_size:
            return self._reject(
                request=request,
                reason=PositionSizingReason.NO_AVAILABLE_CAPACITY,
                limiting_value=(
                    self.policy.max_portfolio_exposure
                ),
            )

        return self._reject(
            request=request,
            reason=PositionSizingReason.NO_AVAILABLE_CAPACITY,
        )

    def _round_down_to_lot(
        self,
        quantity: int,
    ) -> int:
        """数量を最低売買単位へ切り下げる。"""

        return (
            quantity // self.policy.lot_size
        ) * self.policy.lot_size

    def _quantity_for_value(
        self,
        value: float,
        price: float,
    ) -> int:
        """金額上限から最低売買単位で買える数量を返す。"""

        if value <= 0:
            return 0

        raw_quantity = floor(value / price)

        return self._round_down_to_lot(
            raw_quantity
        )

    @staticmethod
    def _reject(
        *,
        request: PositionSizingRequest,
        reason: PositionSizingReason,
        limiting_value: float | None = None,
    ) -> PositionSizingResult:
        """REJECTED結果を生成する。"""

        return PositionSizingResult(
            code=request.code,
            status=PositionSizingStatus.REJECTED,
            reason=reason,
            requested_quantity=request.requested_quantity,
            approved_quantity=0,
            price=request.price,
            approved_order_value=0.0,
            limiting_value=limiting_value,
        )
