"""RuntimeMetricsServiceのテスト。"""

from datetime import datetime, timezone

import pytest

from app.monitoring.runtime_metrics import RuntimeMetricName
from app.monitoring.runtime_metrics_service import (
    RuntimeMetricsService,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def test_increment_snapshot_and_targeted_reset() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )

    assert service.increment(
        RuntimeMetricName.ORDER_CREATED_COUNT
    ) == 1
    assert service.increment(
        RuntimeMetricName.ORDER_CREATED_COUNT,
        amount=2,
    ) == 3
    service.increment(
        RuntimeMetricName.ERROR_OCCURRED_COUNT
    )

    snapshot = service.snapshot()

    assert snapshot.generated_at == NOW
    assert snapshot.get(
        RuntimeMetricName.ORDER_CREATED_COUNT
    ) == 3

    service.reset(
        metric=RuntimeMetricName.ORDER_CREATED_COUNT
    )

    assert service.get(
        RuntimeMetricName.ORDER_CREATED_COUNT
    ) == 0
    assert service.get(
        RuntimeMetricName.ERROR_OCCURRED_COUNT
    ) == 1


def test_reset_all_metrics() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )
    service.increment(
        RuntimeMetricName.SIGNAL_COUNT
    )
    service.increment(
        RuntimeMetricName.EXECUTION_RECORDED_COUNT
    )

    service.reset()

    snapshot = service.snapshot()

    assert all(
        snapshot.get(metric) == 0
        for metric in RuntimeMetricName
    )


def test_increment_rejects_non_positive_amount() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: NOW
    )

    with pytest.raises(
        ValueError,
        match="加算値",
    ):
        service.increment(
            RuntimeMetricName.ERROR_OCCURRED_COUNT,
            amount=0,
        )


def test_snapshot_rejects_naive_clock() -> None:
    service = RuntimeMetricsService(
        now_provider=lambda: datetime(2026, 7, 17)
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        service.snapshot()
