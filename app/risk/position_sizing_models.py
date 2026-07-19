"""Position Sizingに関するドメインモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


MODEL_FILE_VERSION = "sprint77-1-v2"


class PositionSizingStatus(StrEnum):
    """Position Sizingの判定状態。"""

    APPROVED = "approved"
    REDUCED = "reduced"
    REJECTED = "rejected"

    @property
    def is_approved(self) -> bool:
        """注文可能な状態か返す。"""

        return self in {
            PositionSizingStatus.APPROVED,
            PositionSizingStatus.REDUCED,
        }

    @property
    def was_reduced(self) -> bool:
        """希望数量から縮小されたか返す。"""

        return self is PositionSizingStatus.REDUCED


class PositionSizingReason(StrEnum):
    """Position Sizing判定理由。"""

    WITHIN_LIMITS = "within_limits"
    REDUCED_TO_LOT_SIZE = "reduced_to_lot_size"
    REDUCED_BY_POSITION_LIMIT = "reduced_by_position_limit"
    REDUCED_BY_ORDER_LIMIT = "reduced_by_order_limit"
    REDUCED_BY_PORTFOLIO_LIMIT = "reduced_by_portfolio_limit"
    REDUCED_BY_BUYING_POWER = "reduced_by_buying_power"
    MAX_POSITION_COUNT_REACHED = "max_position_count_reached"
    INVALID_PRICE = "invalid_price"
    INSUFFICIENT_BUYING_POWER = "insufficient_buying_power"
    BELOW_MINIMUM_LOT = "below_minimum_lot"
    NO_AVAILABLE_CAPACITY = "no_available_capacity"


@dataclass(frozen=True, slots=True)
class PositionSizingPolicy:
    """Position Sizingに使用する制約。"""

    max_position_count: int
    max_position_value: float
    max_order_value: float
    max_portfolio_exposure: float
    lot_size: int = 100

    def __post_init__(self) -> None:
        """各制約値を検証する。"""

        if self.max_position_count < 1:
            raise ValueError(
                "max_position_countは1以上である必要があります。"
            )

        for name, value in (
            ("max_position_value", self.max_position_value),
            ("max_order_value", self.max_order_value),
            ("max_portfolio_exposure", self.max_portfolio_exposure),
        ):
            if not isfinite(value):
                raise ValueError(
                    f"{name}は有限の数値である必要があります。"
                )

            if value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        if self.lot_size < 1:
            raise ValueError(
                "lot_sizeは1以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class PositionSizingRequest:
    """Position Sizingへの入力。"""

    code: str
    price: float
    requested_quantity: int
    current_position_quantity: int
    current_position_count: int
    current_portfolio_exposure: float
    buying_power: float

    def __post_init__(self) -> None:
        """入力値を検証して正規化する。"""

        normalized_code = self.code.strip()

        if not normalized_code:
            raise ValueError(
                "codeを指定してください。"
            )

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

        if not isfinite(self.price):
            raise ValueError(
                "priceは有限の数値である必要があります。"
            )

        if self.requested_quantity < 1:
            raise ValueError(
                "requested_quantityは1以上である必要があります。"
            )

        if self.current_position_quantity < 0:
            raise ValueError(
                "current_position_quantityは0以上である必要があります。"
            )

        if self.current_position_count < 0:
            raise ValueError(
                "current_position_countは0以上である必要があります。"
            )

        for name, value in (
            (
                "current_portfolio_exposure",
                self.current_portfolio_exposure,
            ),
            ("buying_power", self.buying_power),
        ):
            if not isfinite(value):
                raise ValueError(
                    f"{name}は有限の数値である必要があります。"
                )

            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

    @property
    def opens_new_position(self) -> bool:
        """新規ポジションを開く注文か返す。"""

        return self.current_position_quantity == 0


@dataclass(frozen=True, slots=True)
class PositionSizingResult:
    """Position Sizingの判定結果。"""

    code: str
    status: PositionSizingStatus
    reason: PositionSizingReason
    requested_quantity: int
    approved_quantity: int
    price: float
    approved_order_value: float
    limiting_value: float | None = None

    def __post_init__(self) -> None:
        """判定結果の整合性を検証する。"""

        normalized_code = self.code.strip()

        if not normalized_code:
            raise ValueError(
                "codeを指定してください。"
            )

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

        if self.requested_quantity < 1:
            raise ValueError(
                "requested_quantityは1以上である必要があります。"
            )

        if self.approved_quantity < 0:
            raise ValueError(
                "approved_quantityは0以上である必要があります。"
            )

        if self.approved_quantity > self.requested_quantity:
            raise ValueError(
                "approved_quantityはrequested_quantityを超えられません。"
            )

        if not isfinite(self.price):
            raise ValueError(
                "priceは有限の数値である必要があります。"
            )

        if not isfinite(self.approved_order_value):
            raise ValueError(
                "approved_order_valueは有限の数値である必要があります。"
            )

        expected_value = self.price * self.approved_quantity

        if abs(self.approved_order_value - expected_value) > 1e-9:
            raise ValueError(
                "approved_order_valueがprice×approved_quantityと一致しません。"
            )

        if self.status is PositionSizingStatus.REJECTED:
            if self.approved_quantity != 0:
                raise ValueError(
                    "REJECTEDの場合、approved_quantityは0である必要があります。"
                )
        elif self.approved_quantity == 0:
            raise ValueError(
                "注文可能状態ではapproved_quantityが必要です。"
            )

        if self.status is PositionSizingStatus.APPROVED:
            if self.approved_quantity != self.requested_quantity:
                raise ValueError(
                    "APPROVEDの場合、希望数量と承認数量は一致する必要があります。"
                )

        if self.status is PositionSizingStatus.REDUCED:
            if self.approved_quantity >= self.requested_quantity:
                raise ValueError(
                    "REDUCEDの場合、承認数量は希望数量未満である必要があります。"
                )

        if (
            self.limiting_value is not None
            and not isfinite(self.limiting_value)
        ):
            raise ValueError(
                "limiting_valueは有限の数値である必要があります。"
            )

    @property
    def is_approved(self) -> bool:
        """注文可能な結果か返す。"""

        return self.status.is_approved

    @property
    def was_reduced(self) -> bool:
        """希望数量から縮小されたか返す。"""

        return self.status.was_reduced
