"""執行前リスクフィルタのテスト。"""

from datetime import datetime, timezone

import pytest

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.execution_risk import (
    ExecutionRiskDecision,
    ExecutionRiskPolicy,
    ExecutionRiskReason,
    ExecutionRiskService,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


CURRENT_TIME = datetime(
    2026,
    7,
    16,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_signal(
    *,
    code: str = "7203",
    action: SignalAction = SignalAction.BUY,
    signal_price: float = 2500.0,
    quantity: int = 100,
) -> TradeSignal:
    """リスク判定用シグナルを作成する。"""

    return TradeSignal(
        signal_id=(
            f"signal-{code}-{action.value}"
        ),
        code=code,
        strategy_name="orb",
        action=action,
        generated_at=CURRENT_TIME,
        signal_price=signal_price,
        quantity=quantity,
        reason="opening_range_breakout",
    )


def create_account(
    *,
    cash_balance: float = 3_000_000.0,
    buying_power: float = 3_000_000.0,
    market_value: float = 1_000_000.0,
    equity: float = 4_000_000.0,
) -> BrokerAccountSnapshot:
    """標準口座情報を作成する。"""

    return BrokerAccountSnapshot(
        currency="JPY",
        cash_balance=cash_balance,
        buying_power=buying_power,
        market_value=market_value,
        equity=equity,
        updated_at=CURRENT_TIME,
    )


def create_position(
    *,
    code: str = "8306",
    quantity: int = 100,
    average_price: float = 2000.0,
    market_price: float = 2100.0,
) -> BrokerPosition:
    """標準買いポジションを作成する。"""

    return BrokerPosition(
        code=code,
        side=BrokerPositionSide.LONG,
        quantity=quantity,
        average_price=average_price,
        market_price=market_price,
        updated_at=CURRENT_TIME,
    )


class FakeBroker:
    """固定口座情報を返すリスク判定用Broker。"""

    def __init__(
        self,
        *,
        account: BrokerAccountSnapshot | None = None,
        positions: list[BrokerPosition] | None = None,
    ) -> None:
        """口座情報とポジションを設定する。"""

        self.account = (
            account
            if account is not None
            else create_account()
        )

        self.positions = list(
            positions or []
        )

    def get_account(
        self,
    ) -> BrokerAccountSnapshot:
        """口座情報を返す。"""

        return self.account

    def list_positions(
        self,
    ) -> list[BrokerPosition]:
        """ポジション一覧を返す。"""

        return list(
            self.positions
        )


def test_service_approves_safe_buy() -> None:
    """すべてのリスク条件内の買いを許可する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(),
    )

    result = service.evaluate(
        create_signal()
    )

    assert result.decision is (
        ExecutionRiskDecision.APPROVED
    )
    assert result.is_approved is True
    assert result.is_rejected is False
    assert result.is_failed is False
    assert result.reasons == ()
    assert result.message is None

    assert result.estimated_order_value == pytest.approx(
        250_000.0
    )
    assert result.estimated_cash_after == pytest.approx(
        2_750_000.0
    )
    assert result.estimated_code_market_value == pytest.approx(
        250_000.0
    )
    assert result.estimated_total_market_value == pytest.approx(
        1_250_000.0
    )


def test_service_rejects_order_value_limit() -> None:
    """最大注文金額を超える買いを拒否する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(),
        policy=ExecutionRiskPolicy(
            max_order_value=200_000.0,
        ),
    )

    result = service.evaluate(
        create_signal()
    )

    assert result.is_rejected is True
    assert (
        ExecutionRiskReason.ORDER_VALUE_LIMIT
        in result.reasons
    )


def test_service_rejects_minimum_cash_reserve() -> None:
    """買付後の現金が最低残高を下回る場合を拒否する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            account=create_account(
                cash_balance=600_000.0,
                buying_power=600_000.0,
            )
        ),
        policy=ExecutionRiskPolicy(
            minimum_cash_reserve=500_000.0,
        ),
    )

    result = service.evaluate(
        create_signal()
    )

    assert result.estimated_cash_after == pytest.approx(
        350_000.0
    )
    assert (
        ExecutionRiskReason.CASH_RESERVE_LIMIT
        in result.reasons
    )


def test_service_rejects_existing_long_position() -> None:
    """同一銘柄の買い増し禁止条件を適用する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=[
                create_position(
                    code="7203",
                )
            ]
        )
    )

    result = service.evaluate(
        create_signal(
            code="7203",
        )
    )

    assert (
        ExecutionRiskReason.EXISTING_LONG_POSITION
        in result.reasons
    )


def test_service_allows_additional_buy_when_enabled() -> None:
    """買い増し許可設定なら既存銘柄でも許可する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=[
                create_position(
                    code="7203",
                    quantity=100,
                    market_price=2100.0,
                )
            ]
        ),
        policy=ExecutionRiskPolicy(
            allow_additional_buy=True,
        ),
    )

    result = service.evaluate(
        create_signal(
            code="7203",
        )
    )

    assert (
        ExecutionRiskReason.EXISTING_LONG_POSITION
        not in result.reasons
    )
    assert result.is_approved is True


def test_service_rejects_position_count_limit() -> None:
    """最大保有銘柄数到達時の新規銘柄買いを拒否する。"""

    positions = [
        create_position(
            code="7203",
        ),
        create_position(
            code="8306",
        ),
    ]

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=positions,
        ),
        policy=ExecutionRiskPolicy(
            max_position_count=2,
            allow_additional_buy=True,
        ),
    )

    result = service.evaluate(
        create_signal(
            code="6758",
        )
    )

    assert (
        ExecutionRiskReason.POSITION_COUNT_LIMIT
        in result.reasons
    )


def test_service_rejects_code_exposure_limit() -> None:
    """買い増し後の1銘柄時価上限超過を拒否する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=[
                create_position(
                    code="7203",
                    quantity=100,
                    market_price=2500.0,
                )
            ]
        ),
        policy=ExecutionRiskPolicy(
            max_code_market_value=400_000.0,
            allow_additional_buy=True,
        ),
    )

    result = service.evaluate(
        create_signal(
            code="7203",
        )
    )

    assert result.estimated_code_market_value == pytest.approx(
        500_000.0
    )
    assert (
        ExecutionRiskReason.CODE_EXPOSURE_LIMIT
        in result.reasons
    )


def test_service_rejects_total_exposure_limit() -> None:
    """買付後の口座全体保有時価上限超過を拒否する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            account=create_account(
                market_value=900_000.0,
            )
        ),
        policy=ExecutionRiskPolicy(
            max_total_market_value=1_000_000.0,
        ),
    )

    result = service.evaluate(
        create_signal()
    )

    assert result.estimated_total_market_value == pytest.approx(
        1_150_000.0
    )
    assert (
        ExecutionRiskReason.TOTAL_EXPOSURE_LIMIT
        in result.reasons
    )


def test_service_can_return_multiple_rejection_reasons() -> None:
    """複数のリスク違反をすべて返す。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            account=create_account(
                cash_balance=300_000.0,
                buying_power=300_000.0,
                market_value=900_000.0,
            )
        ),
        policy=ExecutionRiskPolicy(
            max_order_value=200_000.0,
            minimum_cash_reserve=100_000.0,
            max_total_market_value=1_000_000.0,
        ),
    )

    result = service.evaluate(
        create_signal()
    )

    assert result.is_rejected is True
    assert result.reasons == (
        ExecutionRiskReason.ORDER_VALUE_LIMIT,
        ExecutionRiskReason.CASH_RESERVE_LIMIT,
        ExecutionRiskReason.TOTAL_EXPOSURE_LIMIT,
    )
    assert "order_value_limit" in (
        result.message or ""
    )


def test_service_approves_sell_with_sufficient_quantity() -> None:
    """保有数量以内の売りを許可する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=[
                create_position(
                    code="7203",
                    quantity=100,
                    market_price=2500.0,
                )
            ]
        )
    )

    result = service.evaluate(
        create_signal(
            code="7203",
            action=SignalAction.SELL,
            quantity=40,
        )
    )

    assert result.is_approved is True
    assert result.estimated_cash_after == pytest.approx(
        3_100_000.0
    )
    assert result.estimated_code_market_value == pytest.approx(
        150_000.0
    )


def test_service_approves_exit_with_sufficient_quantity() -> None:
    """保有数量以内のEXITシグナルを許可する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=[
                create_position(
                    code="7203",
                    quantity=100,
                )
            ]
        )
    )

    result = service.evaluate(
        create_signal(
            code="7203",
            action=SignalAction.EXIT,
            quantity=100,
        )
    )

    assert result.is_approved is True


def test_service_rejects_insufficient_sell_quantity() -> None:
    """保有数量を超える売りを拒否する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(
            positions=[
                create_position(
                    code="7203",
                    quantity=40,
                )
            ]
        )
    )

    result = service.evaluate(
        create_signal(
            code="7203",
            action=SignalAction.SELL,
            quantity=100,
        )
    )

    assert result.is_rejected is True
    assert result.reasons == (
        ExecutionRiskReason.INSUFFICIENT_SELL_QUANTITY,
    )


def test_service_rejects_sell_without_position() -> None:
    """ポジションがない銘柄の売りを拒否する。"""

    service = ExecutionRiskService(
        broker=FakeBroker(),
    )

    result = service.evaluate(
        create_signal(
            action=SignalAction.SELL,
        )
    )

    assert (
        ExecutionRiskReason.INSUFFICIENT_SELL_QUANTITY
        in result.reasons
    )


class FailingBroker:
    """口座情報取得に失敗するBroker。"""

    def get_account(
        self,
    ) -> BrokerAccountSnapshot:
        """取得失敗を発生させる。"""

        raise RuntimeError(
            "account unavailable"
        )

    def list_positions(
        self,
    ) -> list[BrokerPosition]:
        """空一覧を返す。"""

        return []


def test_service_records_failure_when_continuation_enabled() -> None:
    """判定エラーをFAILED結果へ変換する。"""

    service = ExecutionRiskService(
        broker=FailingBroker(),
    )

    result = service.evaluate(
        create_signal(),
        continue_on_error=True,
    )

    assert result.decision is (
        ExecutionRiskDecision.FAILED
    )
    assert result.is_failed is True
    assert result.reasons == ()
    assert "account unavailable" in (
        result.message or ""
    )


def test_service_raises_failure_when_continuation_disabled() -> None:
    """continue_on_error無効時は取得例外を再送出する。"""

    service = ExecutionRiskService(
        broker=FailingBroker(),
    )

    with pytest.raises(
        RuntimeError,
        match="account unavailable",
    ):
        service.evaluate(
            create_signal(),
            continue_on_error=False,
        )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "max_order_value": 0,
            },
            "最大注文金額",
        ),
        (
            {
                "minimum_cash_reserve": -1,
            },
            "最低現金残高",
        ),
        (
            {
                "max_position_count": 0,
            },
            "最大保有銘柄数",
        ),
        (
            {
                "max_code_market_value": 0,
            },
            "1銘柄最大時価",
        ),
        (
            {
                "max_total_market_value": 0,
            },
            "口座最大保有時価",
        ),
    ],
)
def test_policy_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なリスク制限を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        ExecutionRiskPolicy(
            **arguments
        )