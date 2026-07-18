"""Runtime Health Monitor JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)
from app.runtime.runtime_health_monitor_report import (
    runtime_health_monitor_report_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_report_is_json_compatible() -> None:
    report = RuntimeHealthMonitorReport(
        status=RuntimeHealthStatus.WARNING,
        checked_at=NOW,
        running=True,
        heartbeat_age_seconds=100.0,
        cycle_age_seconds=20.0,
        reasons=("Heartbeatが停滞しています。",),
    )

    payload = runtime_health_monitor_report_to_dict(
        report
    )
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert payload["status"] == "warning"
    assert payload["requires_attention"] is True
    assert "Heartbeat" in serialized
