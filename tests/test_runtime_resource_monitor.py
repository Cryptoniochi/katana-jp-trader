"""Runtime Resource Monitorのテスト。"""

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.runtime.resource_models import (
    RuntimeResourceStatus,
    RuntimeResourceThresholds,
)
from app.runtime.resource_monitor import (
    RuntimeResourceHistory,
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
    def __init__(
        self,
        *,
        cpu: float = 25.0,
        rss: int = 100_000_000,
        vms: int = 200_000_000,
        threads: int = 8,
        created_at: float | None = None,
    ) -> None:
        self.cpu = cpu
        self.rss = rss
        self.vms = vms
        self.threads = threads
        self.created_at = (
            created_at
            if created_at is not None
            else NOW.timestamp() - 3600
        )

    def cpu_percent(self) -> float:
        return self.cpu

    def memory_info(self) -> MemoryInfo:
        return MemoryInfo(
            rss=self.rss,
            vms=self.vms,
        )

    def num_threads(self) -> int:
        return self.threads

    def create_time(self) -> float:
        return self.created_at


def test_monitor_samples_process_and_updates_history() -> None:
    service = RuntimeResourceMonitorService(
        process_reader=FakeProcess(),
        now_provider=lambda: NOW,
    )

    evaluation = service.sample()

    assert evaluation.status is RuntimeResourceStatus.NORMAL
    assert evaluation.snapshot.cpu_percent == 25.0
    assert evaluation.snapshot.rss_bytes == 100_000_000
    assert evaluation.snapshot.vms_bytes == 200_000_000
    assert evaluation.snapshot.thread_count == 8
    assert evaluation.snapshot.process_uptime_seconds == 3600.0
    assert service.latest() == evaluation
    assert service.history_summary().sample_count == 1


def test_monitor_applies_thresholds() -> None:
    service = RuntimeResourceMonitorService(
        process_reader=FakeProcess(
            cpu=95.0,
            rss=50,
            threads=1,
        ),
        thresholds=RuntimeResourceThresholds(
            cpu_warning_percent=50.0,
            cpu_critical_percent=90.0,
            rss_warning_bytes=1000,
            rss_critical_bytes=2000,
            thread_warning_count=10,
            thread_critical_count=20,
        ),
        now_provider=lambda: NOW,
    )

    evaluation = service.sample()

    assert evaluation.status is RuntimeResourceStatus.CRITICAL
    assert evaluation.requires_attention


def test_history_keeps_only_maximum_samples() -> None:
    history = RuntimeResourceHistory(
        maximum_samples=2
    )
    process = FakeProcess()
    service = RuntimeResourceMonitorService(
        process_reader=process,
        history=history,
        now_provider=lambda: NOW,
    )

    process.cpu = 10.0
    first = service.sample()
    process.cpu = 20.0
    second = service.sample()
    process.cpu = 30.0
    third = service.sample()

    assert history.items() == (
        second,
        third,
    )
    assert first not in history.items()


def test_history_summary_calculates_statistics() -> None:
    process = FakeProcess()
    service = RuntimeResourceMonitorService(
        process_reader=process,
        now_provider=lambda: NOW,
    )

    process.cpu = 10.0
    process.rss = 100
    process.vms = 1000
    process.threads = 2
    service.sample()

    process.cpu = 30.0
    process.rss = 300
    process.vms = 2000
    process.threads = 4
    second = service.sample()

    summary = service.history_summary()

    assert summary.sample_count == 2
    assert summary.average_cpu_percent == 20.0
    assert summary.maximum_cpu_percent == 30.0
    assert summary.average_rss_bytes == 200.0
    assert summary.maximum_rss_bytes == 300
    assert summary.maximum_vms_bytes == 2000
    assert summary.maximum_thread_count == 4
    assert summary.latest == second


def test_empty_history_summary_is_zeroed() -> None:
    summary = RuntimeResourceHistory().summary()

    assert summary.sample_count == 0
    assert summary.average_cpu_percent == 0.0
    assert summary.maximum_rss_bytes == 0
    assert summary.latest is None


def test_history_clear_removes_samples() -> None:
    service = RuntimeResourceMonitorService(
        process_reader=FakeProcess(),
        now_provider=lambda: NOW,
    )
    service.sample()

    service.history.clear()

    assert service.history.items() == ()
    assert service.latest() is None


def test_monitor_rejects_naive_clock() -> None:
    service = RuntimeResourceMonitorService(
        process_reader=FakeProcess(),
        now_provider=lambda: datetime(2026, 7, 18),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        service.sample()
