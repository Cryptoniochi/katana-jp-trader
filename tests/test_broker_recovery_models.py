"""BrokerRecoveryResultモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
    BrokerHealthStatus,
)
from app.runtime.broker_recovery_models import (
    BrokerRecoveryResult,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def health(
    *,
    name: str = "fake",
    status: BrokerHealthStatus,
) -> BrokerHealthCheckResult:
    healthy = status is BrokerHealthStatus.HEALTHY

    return BrokerHealthCheckResult(
        broker_name=name,
        status=status,
        checked_at=NOW,
        account_accessible=healthy,
        orders_accessible=healthy,
        positions_accessible=healthy,
        active_order_count=0,
        position_count=0,
        error_messages=(
            ()
            if healthy
            else ("broker unavailable",)
        ),
    )


def test_healthy_result_requires_no_recovery() -> None:
    initial = health(
        status=BrokerHealthStatus.HEALTHY
    )

    result = BrokerRecoveryResult(
        initial_health=initial,
        recovery_result=None,
        final_health=initial,
    )

    assert result.recovery_attempted is False
    assert result.recovered is True


def test_result_rejects_different_broker_names() -> None:
    with pytest.raises(
        ValueError,
        match="Broker名",
    ):
        BrokerRecoveryResult(
            initial_health=health(
                name="first",
                status=BrokerHealthStatus.UNAVAILABLE,
            ),
            recovery_result=None,
            final_health=health(
                name="second",
                status=BrokerHealthStatus.UNAVAILABLE,
            ),
        )
