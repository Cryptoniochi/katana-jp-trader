"""外部送信しない永続Shadow Brokerのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.live.shadow_broker import (
    ShadowBroker,
    ShadowBrokerSettings,
    ShadowOrderConflictError,
    ShadowOrderRecordDecision,
)
from app.trading.broker_adapter import BrokerAdapter
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)


BASE_TIME = datetime(
    2026,
    9,
    30,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_order(
    *,
    order_id: str = "order-001",
    quantity: int = 100,
) -> TradeOrder:
    return TradeOrder(
        order_id=order_id,
        signal_id=f"signal-{order_id}",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
    )


def create_broker(
    tmp_path,
    *,
    current_time: datetime = BASE_TIME,
) -> ShadowBroker:
    return ShadowBroker(
        settings=ShadowBrokerSettings(
            ledger_path=tmp_path / "shadow.jsonl",
            initial_cash=1_000_000.0,
        ),
        now_provider=lambda: current_time,
    )


def test_shadow_broker_satisfies_adapter_contract(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)

    assert isinstance(broker, BrokerAdapter)
    assert broker.broker_name == "shadow"


def test_submit_records_without_fill_or_position(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)

    snapshot = broker.submit_order(create_order())
    account = broker.get_account()

    assert snapshot.status is OrderStatus.QUEUED
    assert snapshot.filled_quantity == 0
    assert snapshot.average_fill_price is None
    assert "no broker request" in (
        snapshot.status_reason or ""
    )
    assert broker.list_positions() == []
    assert account.cash_balance == 1_000_000.0
    assert account.buying_power == 1_000_000.0


def test_record_order_reports_new_and_existing_plan(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)
    order = create_order()

    first = broker.record_order(order)
    second = broker.record_order(order)

    assert (
        first.decision
        is ShadowOrderRecordDecision.RECORDED
    )
    assert (
        second.decision
        is ShadowOrderRecordDecision.EXISTING
    )
    assert first.idempotency_key == second.idempotency_key
    assert broker.get_planned_order(
        first.snapshot.broker_order_id
    ) == order


def test_submit_is_idempotent_in_same_process(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)
    order = create_order()

    first = broker.submit_order(order)
    first_size = broker.settings.ledger_path.stat().st_size
    second = broker.submit_order(order)

    assert second == first
    assert broker.settings.ledger_path.stat().st_size == first_size
    assert len(broker.list_orders()) == 1


def test_ledger_restores_idempotency_after_restart(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)
    order = create_order()
    first = broker.submit_order(order)
    first_size = broker.settings.ledger_path.stat().st_size

    restarted = create_broker(
        tmp_path,
        current_time=BASE_TIME + timedelta(minutes=1),
    )
    second = restarted.submit_order(order)

    assert second == first
    assert restarted.settings.ledger_path.stat().st_size == first_size
    assert len(restarted.list_orders()) == 1


def test_same_order_id_with_different_payload_is_rejected(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)
    broker.submit_order(create_order(quantity=100))

    with pytest.raises(
        ShadowOrderConflictError,
        match="同じ注文ID",
    ):
        broker.submit_order(
            create_order(quantity=200)
        )


def test_cancel_is_persisted_across_restart(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)
    submitted = broker.submit_order(create_order())
    cancelled = broker.cancel_order(
        submitted.broker_order_id
    )

    assert cancelled.status is OrderStatus.CANCELLED
    assert broker.list_orders(active_only=True) == []

    restarted = create_broker(
        tmp_path,
        current_time=BASE_TIME + timedelta(minutes=1),
    )
    restored = restarted.get_order(
        submitted.broker_order_id
    )

    assert restored.status is OrderStatus.CANCELLED
    assert restored.updated_at == BASE_TIME


def test_shadow_ledger_contains_plan_but_no_fill(
    tmp_path,
) -> None:
    broker = create_broker(tmp_path)
    broker.submit_order(create_order())

    content = broker.settings.ledger_path.read_text(
        encoding="utf-8"
    )

    assert '"event":"submitted"' in content
    assert '"code":"7203"' in content
    assert "execution" not in content
    assert "fill_price" not in content
