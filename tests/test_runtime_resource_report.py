"""Runtime Resource JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.resource_models import (
    RuntimeResourceSnapshot,
    RuntimeResourceThresholds,
)
from app.runtime.resource_report import (
    runtime_resource_evaluation_to_dict,
    runtime_resource_snapshot_to_dict,
    runtime_resource_thresholds_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_snapshot_report_is_json_compatible() -> None:
    snapshot = RuntimeResourceSnapshot(
        sampled_at=NOW,
        cpu_percent=25.5,
        rss_bytes=104_857_600,
        vms_bytes=209_715_200,
        thread_count=8,
        process_uptime_seconds=120.0,
    )

    payload = runtime_resource_snapshot_to_dict(
        snapshot
    )
    serialized = json.dumps(payload)

    assert payload["sampled_at"] == NOW.isoformat()
    assert payload["rss_megabytes"] == 100.0
    assert payload["vms_megabytes"] == 200.0
    assert "25.5" in serialized


def test_evaluation_report_contains_status_and_reasons() -> None:
    thresholds = RuntimeResourceThresholds(
        cpu_warning_percent=20.0,
        cpu_critical_percent=90.0,
    )
    snapshot = RuntimeResourceSnapshot(
        sampled_at=NOW,
        cpu_percent=25.5,
        rss_bytes=100,
        vms_bytes=200,
        thread_count=1,
        process_uptime_seconds=120.0,
    )

    payload = runtime_resource_evaluation_to_dict(
        snapshot.evaluate(thresholds)
    )

    assert payload["status"] == "warning"
    assert payload["requires_attention"] is True
    assert len(payload["reasons"]) == 1
    assert payload["snapshot"]["cpu_percent"] == 25.5


def test_threshold_report_contains_all_values() -> None:
    thresholds = RuntimeResourceThresholds(
        cpu_warning_percent=60.0,
        cpu_critical_percent=85.0,
        rss_warning_bytes=1000,
        rss_critical_bytes=2000,
        thread_warning_count=30,
        thread_critical_count=60,
    )

    payload = runtime_resource_thresholds_to_dict(
        thresholds
    )

    assert payload == {
        "cpu_warning_percent": 60.0,
        "cpu_critical_percent": 85.0,
        "rss_warning_bytes": 1000,
        "rss_critical_bytes": 2000,
        "thread_warning_count": 30,
        "thread_critical_count": 60,
    }
