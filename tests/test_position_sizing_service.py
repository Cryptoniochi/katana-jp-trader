"""PositionSizingServiceのテスト。"""

import pytest

TEST_FILE_VERSION = "sprint77-1-v2"

from app.risk.position_sizing_models import (
    PositionSizingPolicy,
    PositionSizingReason,
    PositionSizingRequest,
    PositionSizingStatus,
)
from app.risk.position_sizing_service import PositionSizingService


@pytest.fixture
def policy() -> PositionSizingPolicy:
    """標準テスト用Policyを返す。"""

    return PositionSizingPolicy(
        max_position_count=5,
        max_position_value=500_000.0,
        max_order_value=300_000.0,
        max_portfolio_exposure=1_500_000.0,
        lot_size=100,
    )


@pytest.fixture
def service(
    policy: PositionSizingPolicy,
) -> PositionSizingService:
    """標準テスト用Serviceを返す。"""

    return PositionSizingService(
        policy=policy,
    )


def make_request(
    *,
    code: str = "7203",
    price: float = 1_000.0,
    requested_quantity: int = 200,
    current_position_quantity: int = 0,
    current_position_count: int = 0,
    current_portfolio_exposure: float = 0.0,
    buying_power: float = 1_000_000.0,
) -> PositionSizingRequest:
    """PositionSizingRequestを生成する。"""

    return PositionSizingRequest(
        code=code,
        price=price,
        requested_quantity=requested_quantity,
        current_position_quantity=current_position_quantity,
        current_position_count=current_position_count,
        current_portfolio_exposure=current_portfolio_exposure,
        buying_power=buying_power,
    )


def test_approves_requested_quantity_within_all_limits(
    service: PositionSizingService,
) -> None:
    """全制約内なら希望数量をそのまま承認する。"""

    result = service.calculate(
        make_request(
            requested_quantity=200,
        )
    )

    assert result.status is PositionSizingStatus.APPROVED
    assert result.reason is PositionSizingReason.WITHIN_LIMITS
    assert result.approved_quantity == 200
    assert result.approved_order_value == 200_000.0
    assert result.is_approved
    assert not result.was_reduced


def test_reduces_quantity_to_lot_size(
    service: PositionSizingService,
) -> None:
    """希望数量を売買単位へ切り下げる。"""

    result = service.calculate(
        make_request(
            requested_quantity=250,
        )
    )

    assert result.status is PositionSizingStatus.REDUCED
    assert result.reason is PositionSizingReason.REDUCED_TO_LOT_SIZE
    assert result.approved_quantity == 200
    assert result.approved_order_value == 200_000.0
    assert result.was_reduced


def test_reduces_by_position_limit(
    service: PositionSizingService,
) -> None:
    """1銘柄上限で数量を縮小する。"""

    result = service.calculate(
        make_request(
            requested_quantity=400,
            current_position_quantity=300,
        )
    )

    assert result.status is PositionSizingStatus.REDUCED
    assert result.reason is PositionSizingReason.REDUCED_BY_POSITION_LIMIT
    assert result.approved_quantity == 200
    assert result.approved_order_value == 200_000.0
    assert result.limiting_value == 200_000.0


def test_reduces_by_order_limit(
    service: PositionSizingService,
) -> None:
    """1注文上限で数量を縮小する。"""

    result = service.calculate(
        make_request(
            requested_quantity=500,
        )
    )

    assert result.status is PositionSizingStatus.REDUCED
    assert result.reason is PositionSizingReason.REDUCED_BY_ORDER_LIMIT
    assert result.approved_quantity == 300
    assert result.approved_order_value == 300_000.0
    assert result.limiting_value == 300_000.0


def test_reduces_by_portfolio_limit(
    service: PositionSizingService,
) -> None:
    """Portfolio全体上限で数量を縮小する。"""

    result = service.calculate(
        make_request(
            requested_quantity=400,
            current_portfolio_exposure=1_300_000.0,
        )
    )

    assert result.status is PositionSizingStatus.REDUCED
    assert result.reason is PositionSizingReason.REDUCED_BY_PORTFOLIO_LIMIT
    assert result.approved_quantity == 200
    assert result.approved_order_value == 200_000.0
    assert result.limiting_value == 200_000.0


def test_reduces_by_buying_power(
    service: PositionSizingService,
) -> None:
    """買付余力で数量を縮小する。"""

    result = service.calculate(
        make_request(
            requested_quantity=300,
            buying_power=150_000.0,
        )
    )

    assert result.status is PositionSizingStatus.REDUCED
    assert result.reason is PositionSizingReason.REDUCED_BY_BUYING_POWER
    assert result.approved_quantity == 100
    assert result.approved_order_value == 100_000.0
    assert result.limiting_value == 150_000.0


def test_rejects_invalid_zero_price(
    service: PositionSizingService,
) -> None:
    """株価0円を拒否する。"""

    result = service.calculate(
        make_request(
            price=0.0,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.INVALID_PRICE
    assert result.approved_quantity == 0
    assert result.approved_order_value == 0.0
    assert not result.is_approved


def test_rejects_invalid_negative_price(
    service: PositionSizingService,
) -> None:
    """負の株価を拒否する。"""

    result = service.calculate(
        make_request(
            price=-1.0,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.INVALID_PRICE


@pytest.mark.parametrize(
    "price",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
    ),
)
def test_rejects_non_finite_price(
    price: float,
) -> None:
    """非有限の株価はRequest生成時の入力エラーとして扱う。"""

    with pytest.raises(
        ValueError,
        match="priceは有限の数値である必要があります。",
    ):
        make_request(
            price=price,
        )


def test_rejects_new_position_when_max_count_reached(
    service: PositionSizingService,
) -> None:
    """最大保有銘柄数到達時の新規保有を拒否する。"""

    result = service.calculate(
        make_request(
            current_position_quantity=0,
            current_position_count=5,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.MAX_POSITION_COUNT_REACHED
    assert result.limiting_value == 5.0


def test_allows_additional_order_for_existing_position_at_max_count(
    service: PositionSizingService,
) -> None:
    """最大保有銘柄数到達時でも既存銘柄の買い増しは許可する。"""

    result = service.calculate(
        make_request(
            requested_quantity=100,
            current_position_quantity=100,
            current_position_count=5,
        )
    )

    assert result.status is PositionSizingStatus.APPROVED
    assert result.approved_quantity == 100


@pytest.mark.parametrize(
    "requested_quantity",
    (
        1,
        50,
        99,
    ),
)
def test_rejects_quantity_below_minimum_lot(
    service: PositionSizingService,
    requested_quantity: int,
) -> None:
    """最低売買単位未満の希望数量を拒否する。"""

    result = service.calculate(
        make_request(
            requested_quantity=requested_quantity,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.BELOW_MINIMUM_LOT
    assert result.approved_quantity == 0
    assert result.limiting_value == 100.0


def test_rejects_when_buying_power_is_below_one_lot(
    service: PositionSizingService,
) -> None:
    """買付余力が最低売買単位分に満たなければ拒否する。"""

    result = service.calculate(
        make_request(
            buying_power=99_999.0,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.INSUFFICIENT_BUYING_POWER
    assert result.limiting_value == 99_999.0


def test_rejects_when_position_has_no_available_capacity(
    service: PositionSizingService,
) -> None:
    """1銘柄上限まで保有済みなら拒否する。"""

    result = service.calculate(
        make_request(
            current_position_quantity=500,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.NO_AVAILABLE_CAPACITY
    assert result.limiting_value == 500_000.0


def test_rejects_when_portfolio_has_no_available_capacity(
    service: PositionSizingService,
) -> None:
    """Portfolio上限まで投資済みなら拒否する。"""

    result = service.calculate(
        make_request(
            current_portfolio_exposure=1_500_000.0,
        )
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.NO_AVAILABLE_CAPACITY
    assert result.limiting_value == 1_500_000.0


def test_rejects_when_order_limit_is_below_one_lot() -> None:
    """1注文上限が最低売買単位分に満たなければ拒否する。"""

    service = PositionSizingService(
        policy=PositionSizingPolicy(
            max_position_count=5,
            max_position_value=500_000.0,
            max_order_value=99_999.0,
            max_portfolio_exposure=1_500_000.0,
            lot_size=100,
        )
    )

    result = service.calculate(
        make_request()
    )

    assert result.status is PositionSizingStatus.REJECTED
    assert result.reason is PositionSizingReason.BELOW_MINIMUM_LOT
    assert result.limiting_value == 99_999.0


def test_approves_exact_limit_boundary(
    service: PositionSizingService,
) -> None:
    """上限ちょうどの数量を承認する。"""

    result = service.calculate(
        make_request(
            requested_quantity=300,
            buying_power=300_000.0,
        )
    )

    assert result.status is PositionSizingStatus.APPROVED
    assert result.approved_quantity == 300
    assert result.approved_order_value == 300_000.0


@pytest.mark.parametrize(
    ("requested_quantity", "approved_quantity"),
    (
        (100, 100),
        (199, 100),
        (200, 200),
        (299, 200),
    ),
)
def test_lot_size_boundaries(
    service: PositionSizingService,
    requested_quantity: int,
    approved_quantity: int,
) -> None:
    """売買単位境界で承認数量を正しく計算する。"""

    result = service.calculate(
        make_request(
            requested_quantity=requested_quantity,
        )
    )

    assert result.approved_quantity == approved_quantity

    if requested_quantity == approved_quantity:
        assert result.status is PositionSizingStatus.APPROVED
    else:
        assert result.status is PositionSizingStatus.REDUCED
        assert result.reason is PositionSizingReason.REDUCED_TO_LOT_SIZE


def test_smallest_capacity_wins(
    service: PositionSizingService,
) -> None:
    """複数制約のうち最も厳しい数量を採用する。"""

    result = service.calculate(
        make_request(
            requested_quantity=500,
            current_position_quantity=200,
            current_portfolio_exposure=1_250_000.0,
            buying_power=150_000.0,
        )
    )

    assert result.status is PositionSizingStatus.REDUCED
    assert result.approved_quantity == 100
    assert result.reason is PositionSizingReason.REDUCED_BY_BUYING_POWER


def test_custom_lot_size_is_supported() -> None:
    """任意の売買単位で数量を計算できる。"""

    service = PositionSizingService(
        policy=PositionSizingPolicy(
            max_position_count=5,
            max_position_value=100_000.0,
            max_order_value=100_000.0,
            max_portfolio_exposure=500_000.0,
            lot_size=1,
        )
    )

    result = service.calculate(
        make_request(
            price=1_000.0,
            requested_quantity=25,
        )
    )

    assert result.status is PositionSizingStatus.APPROVED
    assert result.approved_quantity == 25
    assert result.approved_order_value == 25_000.0
