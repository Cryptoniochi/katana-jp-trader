"""Runtime Resourceモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.runtime.resource_models import (
    RuntimeResourceEvaluation,
    RuntimeResourceSnapshot,
    RuntimeResourceStatus,
    RuntimeResourceThresholds,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def snapshot(
    *,
    cpu_percent: float = 20.0,
    rss_bytes: int = 500_000_000,
    thread_count: int = 10,
) -> RuntimeResourceSnapshot:
    return RuntimeResourceSnapshot(
        sampled_at=NOW,
        cpu_percent=cpu_percent,
        rss_bytes=rss_bytes,
        vms_bytes=1_000_000_000,
        thread_count=thread_count,
        process_uptime_seconds=3600.0,
    )


def test_thresholds_validate_ranges_and_order() -> None:
    with pytest.raises(ValueError, match="100以下"):
        RuntimeResourceThresholds(
            cpu_warning_percent=101.0
        )

    with pytest.raises(ValueError, match="以上"):
        RuntimeResourceThresholds(
            cpu_warning_percent=80.0,
            cpu_critical_percent=70.0,
        )

    with pytest.raises(ValueError, match="RSS重大値"):
        RuntimeResourceThresholds(
            rss_warning_bytes=200,
            rss_critical_bytes=100,
        )


def test_snapshot_converts_bytes_to_megabytes() -> None:
    value = RuntimeResourceSnapshot(
        sampled_at=NOW,
        cpu_percent=10.0,
        rss_bytes=104_857_600,
        vms_bytes=209_715_200,
        thread_count=5,
        process_uptime_seconds=60.0,
    )

    assert value.rss_megabytes == 100.0
    assert value.vms_megabytes == 200.0


def test_snapshot_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="CPU使用率"):
        RuntimeResourceSnapshot(
            sampled_at=NOW,
            cpu_percent=-1.0,
            rss_bytes=0,
            vms_bytes=0,
            thread_count=0,
            process_uptime_seconds=0.0,
        )

    with pytest.raises(ValueError, match="タイムゾーン"):
        RuntimeResourceSnapshot(
            sampled_at=datetime(2026, 7, 18),
            cpu_percent=0.0,
            rss_bytes=0,
            vms_bytes=0,
            thread_count=0,
            process_uptime_seconds=0.0,
        )


def test_normal_snapshot_evaluates_as_normal() -> None:
    evaluation = snapshot().evaluate(
        RuntimeResourceThresholds()
    )

    assert evaluation.status is RuntimeResourceStatus.NORMAL
    assert evaluation.reasons == ()
    assert evaluation.requires_attention is False


def test_warning_snapshot_collects_reasons() -> None:
    thresholds = RuntimeResourceThresholds(
        cpu_warning_percent=50.0,
        cpu_critical_percent=90.0,
        rss_warning_bytes=600_000_000,
        rss_critical_bytes=900_000_000,
        thread_warning_count=20,
        thread_critical_count=40,
    )
    evaluation = snapshot(
        cpu_percent=60.0,
        rss_bytes=700_000_000,
        thread_count=25,
    ).evaluate(thresholds)

    assert evaluation.status is RuntimeResourceStatus.WARNING
    assert len(evaluation.reasons) == 3
    assert evaluation.requires_attention


def test_critical_metric_sets_overall_critical() -> None:
    thresholds = RuntimeResourceThresholds(
        cpu_warning_percent=50.0,
        cpu_critical_percent=90.0,
        rss_warning_bytes=600_000_000,
        rss_critical_bytes=900_000_000,
        thread_warning_count=20,
        thread_critical_count=40,
    )
    evaluation = snapshot(
        cpu_percent=95.0,
        rss_bytes=700_000_000,
        thread_count=25,
    ).evaluate(thresholds)

    assert evaluation.status is RuntimeResourceStatus.CRITICAL
    assert any(
        "CPU使用率が重大閾値以上" in reason
        for reason in evaluation.reasons
    )


def test_evaluation_rejects_inconsistent_status() -> None:
    with pytest.raises(ValueError, match="理由"):
        RuntimeResourceEvaluation(
            snapshot=snapshot(),
            status=RuntimeResourceStatus.WARNING,
            reasons=(),
        )
