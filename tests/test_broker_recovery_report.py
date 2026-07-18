"""BrokerRecoveryResult JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.broker.broker_health_models import (
    BrokerHealthCheckResult,
    BrokerHealthStatus,
)
from app.runtime.broker_recovery_models import (
    BrokerRecoveryResult,
)
from app.runtime.broker_recovery_report import (
    broker_recovery_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_broker_recovery_result_is_json_compatible() -> None:
    health = BrokerHealthCheckResult(
        broker_name="paper",
        status=BrokerHealthStatus.HEALTHY,
        checked_at=NOW,
        account_accessible=True,
        orders_accessible=True,
        positions_accessible=True,
        active_order_count=0,
        position_count=0,
        error_messages=(),
    )
    result = BrokerRecoveryResult(
        initial_health=health,
        recovery_result=None,
        final_health=health,
    )

    payload = broker_recovery_result_to_dict(
        result
    )
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert payload["broker_name"] == "paper"
    assert payload["recovery_attempted"] is False
    assert payload["recovered"] is True
    assert "paper" in serialized
