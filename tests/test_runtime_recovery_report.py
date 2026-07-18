"""RuntimeRecoveryResult JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)
from app.runtime.runtime_recovery_models import (
    RuntimeRecoveryResult,
)
from app.runtime.runtime_recovery_report import (
    runtime_recovery_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_runtime_recovery_result_is_json_compatible() -> None:
    health = RuntimeHealthMonitorReport(
        status=RuntimeHealthStatus.HEALTHY,
        checked_at=NOW,
        running=True,
        heartbeat_age_seconds=10.0,
        cycle_age_seconds=20.0,
        reasons=(),
    )
    result = RuntimeRecoveryResult(
        runtime_name="paper-runtime",
        initial_health=health,
        recovery_result=None,
        final_health=health,
    )

    payload = runtime_recovery_result_to_dict(
        result
    )
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert payload["runtime_name"] == "paper-runtime"
    assert payload["recovery_attempted"] is False
    assert payload["recovered"] is True
    assert payload["requires_attention"] is False
    assert "paper-runtime" in serialized
