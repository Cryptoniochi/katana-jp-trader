"""Runtime Resource履歴レポートのテスト。"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app.runtime.resource_history_report import (
    runtime_resource_history_summary_to_dict,
)
from app.runtime.resource_monitor import (
    RuntimeResourceMonitorService,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


@dataclass
class MemoryInfo:
    rss: int
    vms: int


class FakeProcess:
    def cpu_percent(self) -> float:
        return 25.0

    def memory_info(self) -> MemoryInfo:
        return MemoryInfo(
            rss=104_857_600,
            vms=209_715_200,
        )

    def num_threads(self) -> int:
        return 8

    def create_time(self) -> float:
        return NOW.timestamp() - 120


def test_history_summary_report_is_json_compatible() -> None:
    service = RuntimeResourceMonitorService(
        process_reader=FakeProcess(),
        now_provider=lambda: NOW,
    )
    service.sample()

    payload = runtime_resource_history_summary_to_dict(
        service.history_summary()
    )
    serialized = json.dumps(payload)

    assert payload["sample_count"] == 1
    assert payload["average_cpu_percent"] == 25.0
    assert payload["maximum_rss_bytes"] == 104_857_600
    assert payload["latest"]["snapshot"][
        "process_uptime_seconds"
    ] == 120.0
    assert "normal" in serialized


def test_empty_history_report_has_null_latest() -> None:
    service = RuntimeResourceMonitorService(
        process_reader=FakeProcess(),
        now_provider=lambda: NOW,
    )

    payload = runtime_resource_history_summary_to_dict(
        service.history_summary()
    )

    assert payload["sample_count"] == 0
    assert payload["latest"] is None
