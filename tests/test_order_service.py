"""売買シグナルから注文を作成するサービスのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)
from app.trading.order_repository import (
    OrderRepository,
)
from app.trading.order_service import (
    SignalNotOrderableError,
    SignalOrderConflictError,
    SignalOrderConsistencyError,
    SignalOrderCreationDecision,
    SignalOrderService,
    SignalOrderServiceSettings,
)
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
)
from app.trading.signal_repository import (
    SignalNotFoundError,
    SignalRepository,
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
    signal_id: str = "signal-001",
    code: str = "7203",
    action: SignalAction = SignalAction.BUY,
    quantity: int = 100,
) -> TradeSignal:
    """注文作成用の売買シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name="orb",
        action=action,
        generated_at=CURRENT_TIME,
        signal_price=2500.0,
        quantity=quantity,
        reason="opening_range_breakout",
        confidence=0.8,
    )


def create_environment(
    tmp_path: Path,
    *,
    signal: TradeSignal | None = None,
) -> tuple[
    SignalRepository,
    OrderRepository,
    SignalOrderService,
]:
    """実SQLiteを使用する注文作成環境を作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    signal_repository = SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    order_repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    if signal is not None:
        signal_repository.save(
            signal,
        )

    service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
    )

    return (
        signal_repository,
        order_repository,
        service,
    )


def test_service_creates_market_buy_order(
    tmp_path: Path,
) -> None:
    """BUYシグナルから成行買い注文を作成する。"""

    signal_repository, order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    result = service.create_from_signal(
        "signal-001",
    )

    assert result.decision is (
        SignalOrderCreationDecision.CREATED
    )
    assert result.was_created is True
    assert result.was_existing is False
    assert result.is_failed is False
    assert result.message is None

    assert result.order_record is not None
    assert result.signal_record is not None

    order = result.order_record

    assert order.signal_id == "signal-001"
    assert order.code == "7203"
    assert order.order.side is OrderSide.BUY
    assert order.order.order_type is OrderType.MARKET
    assert order.order.quantity == 100
    assert order.status is OrderStatus.NEW

    signal = result.signal_record

    assert signal.status is SignalStatus.PROCESSED
    assert signal.process_note == (
        "trade order created"
    )

    assert order_repository.count() == 1
    assert signal_repository.count(
        status=SignalStatus.PROCESSED,
    ) == 1


def test_service_maps_sell_signal_to_sell_order(
    tmp_path: Path,
) -> None:
    """SELLシグナルを売り注文へ変換する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(
                action=SignalAction.SELL,
            ),
        )
    )

    result = service.create_from_signal(
        "signal-001",
    )

    assert result.order_record is not None
    assert result.order_record.order.side is (
        OrderSide.SELL
    )


def test_service_maps_exit_signal_to_sell_order(
    tmp_path: Path,
) -> None:
    """EXITシグナルを売り注文へ変換する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(
                action=SignalAction.EXIT,
            ),
        )
    )

    result = service.create_from_signal(
        "signal-001",
    )

    assert result.order_record is not None
    assert result.order_record.order.side is (
        OrderSide.SELL
    )


def test_service_creates_limit_order(
    tmp_path: Path,
) -> None:
    """シグナルから指値注文を作成する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    result = service.create_from_signal(
        "signal-001",
        order_type=OrderType.LIMIT,
        limit_price=2495.0,
    )

    assert result.order_record is not None

    order = result.order_record.order

    assert order.order_type is OrderType.LIMIT
    assert order.limit_price == pytest.approx(
        2495.0,
    )
    assert order.stop_price is None


def test_service_creates_stop_limit_order(
    tmp_path: Path,
) -> None:
    """シグナルから逆指値付き指値注文を作成する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    result = service.create_from_signal(
        "signal-001",
        order_type=OrderType.STOP_LIMIT,
        limit_price=2510.0,
        stop_price=2505.0,
    )

    assert result.order_record is not None

    order = result.order_record.order

    assert order.order_type is OrderType.STOP_LIMIT
    assert order.limit_price == pytest.approx(
        2510.0,
    )
    assert order.stop_price == pytest.approx(
        2505.0,
    )


def test_service_generates_deterministic_order_id(
    tmp_path: Path,
) -> None:
    """同一シグナルから再現可能な注文IDを生成する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    first_result = service.create_from_signal(
        "signal-001",
    )
    second_result = service.create_from_signal(
        "signal-001",
    )

    assert first_result.order_record is not None
    assert second_result.order_record is not None

    assert (
        first_result.order_record.order_id
        == second_result.order_record.order_id
    )
    assert first_result.order_record.order_id.startswith(
        "order-"
    )


def test_service_is_idempotent_for_processed_signal(
    tmp_path: Path,
) -> None:
    """同じ処理を再実行しても注文を重複作成しない。"""

    signal_repository, order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    first = service.create_from_signal(
        "signal-001",
    )
    second = service.create_from_signal(
        "signal-001",
    )

    assert first.was_created is True
    assert second.was_existing is True
    assert second.decision is (
        SignalOrderCreationDecision.EXISTING
    )

    assert order_repository.count() == 1
    assert signal_repository.count(
        status=SignalStatus.PROCESSED,
    ) == 1


def test_service_recovers_order_created_signal_pending_state(
    tmp_path: Path,
) -> None:
    """注文だけ保存済みの中断状態を再実行で復旧する。"""

    signal_repository, order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    expected_order_id = (
        service
        ._create_order_id(
            "signal-001",
        )
    )

    existing_order = order_repository.create(
        TradeOrder(
            order_id=expected_order_id,
            signal_id="signal-001",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
    )

    pending_signal = signal_repository.get(
        "signal-001",
    )

    assert pending_signal.status is SignalStatus.PENDING

    result = service.create_from_signal(
        "signal-001",
    )

    assert result.was_existing is True
    assert result.order_record == existing_order
    assert result.signal_record is not None
    assert result.signal_record.status is (
        SignalStatus.PROCESSED
    )

    assert order_repository.count() == 1


def test_service_rejects_cancelled_signal(
    tmp_path: Path,
) -> None:
    """取消済みシグナルからの注文作成を拒否する。"""

    signal_repository, order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    signal_repository.cancel(
        "signal-001",
        process_note="risk rejected",
    )

    with pytest.raises(
        SignalNotOrderableError,
        match="取消済み",
    ):
        service.create_from_signal(
            "signal-001",
        )

    assert order_repository.count() == 0


def test_service_rejects_processed_signal_without_order(
    tmp_path: Path,
) -> None:
    """処理済みなのに注文がない不整合を拒否する。"""

    signal_repository, order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    signal_repository.mark_processed(
        "signal-001",
        process_note="incorrect manual update",
    )

    with pytest.raises(
        SignalOrderConsistencyError,
        match="注文が存在しません",
    ):
        service.create_from_signal(
            "signal-001",
        )

    assert order_repository.count() == 0


def test_service_rejects_existing_order_with_different_terms(
    tmp_path: Path,
) -> None:
    """既存注文と今回の注文条件が異なる場合を拒否する。"""

    _signal_repository, order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    order_repository.create(
        TradeOrder(
            order_id=service._create_order_id(
                "signal-001",
            ),
            signal_id="signal-001",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=2490.0,
        )
    )

    with pytest.raises(
        SignalOrderConflictError,
        match="一致しません",
    ):
        service.create_from_signal(
            "signal-001",
            order_type=OrderType.MARKET,
        )

    assert order_repository.count() == 1


def test_service_rejects_missing_signal(
    tmp_path: Path,
) -> None:
    """存在しないシグナルIDを拒否する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
        )
    )

    with pytest.raises(
        SignalNotFoundError,
        match="存在しません",
    ):
        service.create_from_signal(
            "missing-signal",
        )


def test_service_records_failure_when_continuation_enabled(
    tmp_path: Path,
) -> None:
    """continue_on_error有効時は例外を失敗結果へ変換する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
        )
    )

    result = service.create_from_signal(
        "missing-signal",
        continue_on_error=True,
    )

    assert result.decision is (
        SignalOrderCreationDecision.FAILED
    )
    assert result.is_failed is True
    assert result.signal_record is None
    assert result.order_record is None
    assert "存在しません" in (
        result.message or ""
    )


def test_service_uses_custom_settings(
    tmp_path: Path,
) -> None:
    """注文IDと処理メモの共通設定を適用する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    signal_repository = SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )
    order_repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    signal_repository.save(
        create_signal(),
    )

    service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
        settings=SignalOrderServiceSettings(
            order_id_prefix="katana-order",
            processed_note="order prepared",
        ),
    )

    result = service.create_from_signal(
        "signal-001",
    )

    assert result.order_record is not None
    assert result.signal_record is not None

    assert result.order_record.order_id.startswith(
        "katana-order-"
    )
    assert result.signal_record.process_note == (
        "order prepared"
    )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "order_id_prefix": " ",
            },
            "注文IDプレフィックス",
        ),
        (
            {
                "processed_note": " ",
            },
            "シグナル処理メモ",
        ),
    ],
)
def test_service_settings_reject_invalid_values(
    arguments: dict[str, str],
    message: str,
) -> None:
    """不正な注文作成設定を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        SignalOrderServiceSettings(
            **arguments,
        )


def test_service_delegates_order_validation(
    tmp_path: Path,
) -> None:
    """不正な注文価格条件をTradeOrderの検証で拒否する。"""

    _signal_repository, _order_repository, service = (
        create_environment(
            tmp_path,
            signal=create_signal(),
        )
    )

    with pytest.raises(
        ValueError,
        match="指値価格",
    ):
        service.create_from_signal(
            "signal-001",
            order_type=OrderType.LIMIT,
        )