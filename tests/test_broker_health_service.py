"""BrokerHealthServiceのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.broker.broker_health_models import (
    BrokerHealthStatus,
)
from app.broker.broker_health_service import (
    BrokerHealthService,
)


CHECKED_AT = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


class FakeBroker:
    """診断用Broker Adapter。"""

    broker_name = "fake"

    def __init__(self) -> None:
        self.fail_account = False
        self.fail_orders = False
        self.fail_positions = False

    def submit_order(self, order):
        return order

    def cancel_order(self, broker_order_id):
        return broker_order_id

    def get_order(self, broker_order_id):
        return broker_order_id

    def get_account(self):
        if self.fail_account:
            raise RuntimeError("account failed")

        return object()

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ):
        if self.fail_orders:
            raise RuntimeError("orders failed")

        return [object()] if active_only else []

    def list_positions(self):
        if self.fail_positions:
            raise RuntimeError("positions failed")

        return [object(), object()]


def service() -> BrokerHealthService:
    """固定時計の診断サービスを返す。"""

    return BrokerHealthService(
        now_provider=lambda: CHECKED_AT
    )


def test_inspect_complete_capabilities() -> None:
    """全必須メソッドを実装したBrokerを検出する。"""

    result = service().inspect_capabilities(
        FakeBroker()
    )

    assert result.broker_name == "fake"
    assert result.is_complete


def test_inspect_missing_capabilities() -> None:
    """不足メソッドをFalseとして返す。"""

    class ReadOnlyBroker:
        broker_name = "readonly"

        def get_account(self):
            return object()

        def list_orders(
            self,
            *,
            active_only: bool = False,
        ):
            return []

        def list_positions(self):
            return []

    result = service().inspect_capabilities(
        ReadOnlyBroker()
    )

    assert result.is_complete is False
    assert result.submit_order is False
    assert result.cancel_order is False
    assert result.get_account is True


def test_check_healthy_broker() -> None:
    """全照会成功時はhealthyを返す。"""

    result = service().check(FakeBroker())

    assert result.status is BrokerHealthStatus.HEALTHY
    assert result.is_healthy
    assert result.active_order_count == 1
    assert result.position_count == 2
    assert result.error_messages == ()
    assert result.checked_at == CHECKED_AT


def test_check_degraded_broker() -> None:
    """一部照会失敗時はdegradedを返す。"""

    broker = FakeBroker()
    broker.fail_orders = True

    result = service().check(broker)

    assert result.status is BrokerHealthStatus.DEGRADED
    assert result.account_accessible
    assert result.orders_accessible is False
    assert result.positions_accessible
    assert result.active_order_count == 0
    assert "orders failed" in result.error_messages[0]


def test_check_unavailable_broker() -> None:
    """全照会失敗時はunavailableを返す。"""

    broker = FakeBroker()
    broker.fail_account = True
    broker.fail_orders = True
    broker.fail_positions = True

    result = service().check(broker)

    assert result.status is (
        BrokerHealthStatus.UNAVAILABLE
    )
    assert result.is_unavailable
    assert len(result.error_messages) == 3


def test_require_ready_returns_healthy_result() -> None:
    """機能と接続が完全なBrokerを受け入れる。"""

    result = service().require_ready(
        FakeBroker()
    )

    assert result.is_healthy


def test_require_ready_rejects_missing_method() -> None:
    """必須メソッド不足を拒否する。"""

    class IncompleteBroker:
        broker_name = "incomplete"

    with pytest.raises(
        RuntimeError,
        match="必須機能",
    ):
        service().require_ready(
            IncompleteBroker()
        )


def test_require_ready_rejects_degraded_broker() -> None:
    """一部照会失敗のBrokerを拒否する。"""

    broker = FakeBroker()
    broker.fail_positions = True

    with pytest.raises(
        RuntimeError,
        match="ヘルスチェック",
    ):
        service().require_ready(broker)


def test_service_rejects_naive_clock() -> None:
    """タイムゾーンなし確認日時を拒否する。"""

    broker = FakeBroker()

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        BrokerHealthService(
            now_provider=lambda: datetime(
                2026,
                7,
                17,
            )
        ).check(broker)
