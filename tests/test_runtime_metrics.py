"""RuntimeMetricsSnapshotのテスト。"""

from datetime import datetime, timezone

import pytest

from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
    RuntimeMetricsSnapshot,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def test_snapshot_fills_missing_metrics_and_calculates_rates() -> None:
    snapshot = RuntimeMetricsSnapshot(
        generated_at=NOW,
        counts={
            RuntimeMetricName.DOMAIN_EVENT_COUNT: 10,
            RuntimeMetricName.ERROR_OCCURRED_COUNT: 2,
            RuntimeMetricName.NOTIFICATION_DELIVERED_COUNT: 3,
            RuntimeMetricName.NOTIFICATION_FAILED_COUNT: 1,
        },
    )

    assert snapshot.get(
        RuntimeMetricName.ORDER_CREATED_COUNT
    ) == 0
    assert snapshot.error_rate == pytest.approx(0.2)
    assert snapshot.notification_attempt_count == 4
    assert snapshot.notification_failure_rate == pytest.approx(
        0.25
    )


def test_snapshot_uses_defensive_copy() -> None:
    counts = {
        RuntimeMetricName.DOMAIN_EVENT_COUNT: 1,
    }

    snapshot = RuntimeMetricsSnapshot(
        generated_at=NOW,
        counts=counts,
    )
    counts[
        RuntimeMetricName.DOMAIN_EVENT_COUNT
    ] = 99

    assert snapshot.domain_event_count == 1


def test_snapshot_rejects_invalid_values() -> None:
    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        RuntimeMetricsSnapshot(
            generated_at=datetime(2026, 7, 17),
            counts={},
        )

    with pytest.raises(
        ValueError,
        match="0以上",
    ):
        RuntimeMetricsSnapshot(
            generated_at=NOW,
            counts={
                RuntimeMetricName.ERROR_OCCURRED_COUNT: -1,
            },
        )


def test_zero_denominators_return_zero() -> None:
    snapshot = RuntimeMetricsSnapshot(
        generated_at=NOW,
        counts={},
    )

    assert snapshot.error_rate == 0.0
    assert snapshot.notification_failure_rate == 0.0
