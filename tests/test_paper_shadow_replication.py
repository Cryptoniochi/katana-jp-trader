"""Paper注文からShadow注文計画への安全な複製テスト。"""

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.paper_shadow_replication import (
    PaperShadowReplicationDecision,
    PaperShadowReplicationService,
)
from app.live.shadow_broker import (
    ShadowBroker,
    ShadowBrokerSettings,
    ShadowOrderRecordDecision,
    ShadowOrderRecordResult,
)
from app.trading.broker_adapter import BrokerOrderSnapshot
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
    30,
    tzinfo=timezone.utc,
)


def create_order(
    *,
    order_id: str = "paper-order-001",
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


def execution_item(
    order: TradeOrder,
    *,
    failed: bool = False,
    has_broker_result: bool = True,
):
    return SimpleNamespace(
        queued_order=SimpleNamespace(
            order_record=SimpleNamespace(
                order=order
            )
        ),
        is_failed=failed,
        broker_sync_result=(
            object()
            if has_broker_result
            else None
        ),
        message=(
            "paper broker failed"
            if failed
            else None
        ),
    )


def execution_batch(*items):
    return SimpleNamespace(items=tuple(items))


def create_shadow_broker(tmp_path) -> ShadowBroker:
    return ShadowBroker(
        settings=ShadowBrokerSettings(
            ledger_path=tmp_path / "shadow.jsonl"
        ),
        now_provider=lambda: BASE_TIME,
    )


def test_replicates_only_paper_order_that_reached_broker(
    tmp_path,
) -> None:
    shadow = create_shadow_broker(tmp_path)
    service = PaperShadowReplicationService(
        shadow_recorder=shadow
    )
    approved = create_order(order_id="approved")
    failed = create_order(order_id="failed")

    result = service.replicate(
        execution_batch(
            execution_item(approved),
            execution_item(failed, failed=True),
        )
    )

    assert result.input_count == 2
    assert result.recorded_count == 1
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert result.is_consistent
    assert shadow.list_orders()[0].client_order_id == (
        approved.order_id
    )


def test_replication_is_idempotent_across_retries(
    tmp_path,
) -> None:
    shadow = create_shadow_broker(tmp_path)
    service = PaperShadowReplicationService(
        shadow_recorder=shadow
    )
    batch = execution_batch(
        execution_item(create_order())
    )

    first = service.replicate(batch)
    first_size = shadow.settings.ledger_path.stat().st_size
    second = service.replicate(batch)

    assert first.recorded_count == 1
    assert second.existing_count == 1
    assert shadow.settings.ledger_path.stat().st_size == first_size
    assert len(shadow.list_orders()) == 1


def test_empty_risk_blocked_batch_records_nothing(
    tmp_path,
) -> None:
    shadow = create_shadow_broker(tmp_path)
    service = PaperShadowReplicationService(
        shadow_recorder=shadow
    )

    result = service.replicate(execution_batch())

    assert result.input_count == 0
    assert result.replicated_count == 0
    assert result.is_consistent
    assert not shadow.settings.ledger_path.exists()


class FailingShadowRecorder:
    """Shadow障害を再現する。"""

    def record_order(self, order):
        del order
        raise OSError("shadow disk unavailable")


def test_shadow_failure_is_isolated_from_paper_result() -> None:
    service = PaperShadowReplicationService(
        shadow_recorder=FailingShadowRecorder()
    )
    paper_batch = execution_batch(
        execution_item(create_order())
    )

    result = service.replicate(paper_batch)

    assert paper_batch.items[0].is_failed is False
    assert result.failed_count == 1
    assert result.is_consistent is False
    assert "disk unavailable" in (
        result.items[0].message or ""
    )


def test_shadow_failure_can_be_strict_for_offline_validation() -> None:
    service = PaperShadowReplicationService(
        shadow_recorder=FailingShadowRecorder()
    )

    with pytest.raises(
        OSError,
        match="disk unavailable",
    ):
        service.replicate(
            execution_batch(
                execution_item(create_order())
            ),
            continue_on_error=False,
        )


class MismatchingShadowRecorder:
    """異なる注文を返して照合失敗を再現する。"""

    def record_order(
        self,
        order: TradeOrder,
    ) -> ShadowOrderRecordResult:
        different = replace(order, quantity=200)
        snapshot = BrokerOrderSnapshot(
            broker_order_id="shadow-mismatch",
            client_order_id=different.order_id,
            code=different.code,
            side=different.side,
            status=OrderStatus.QUEUED,
            quantity=different.quantity,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=BASE_TIME,
            updated_at=BASE_TIME,
        )
        return ShadowOrderRecordResult(
            decision=ShadowOrderRecordDecision.RECORDED,
            order=different,
            idempotency_key="mismatch",
            snapshot=snapshot,
        )


def test_detects_paper_shadow_order_mismatch() -> None:
    service = PaperShadowReplicationService(
        shadow_recorder=MismatchingShadowRecorder()
    )

    result = service.replicate(
        execution_batch(
            execution_item(create_order())
        )
    )

    assert result.mismatch_count == 1
    assert result.is_consistent is False
    assert (
        result.items[0].decision
        is PaperShadowReplicationDecision.MISMATCH
    )


def test_skips_item_without_broker_sync_result(
    tmp_path,
) -> None:
    shadow = create_shadow_broker(tmp_path)
    service = PaperShadowReplicationService(
        shadow_recorder=shadow
    )

    result = service.replicate(
        execution_batch(
            execution_item(
                create_order(),
                has_broker_result=False,
            )
        )
    )

    assert result.skipped_count == 1
    assert result.replicated_count == 0
    assert shadow.list_orders() == []
