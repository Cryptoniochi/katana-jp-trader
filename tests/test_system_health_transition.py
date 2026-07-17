"""SystemHealthTransitionDetectorのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.monitoring.runtime_metrics import (
    RuntimeMetricsSnapshot,
)
from app.monitoring.system_health_models import (
    SystemHealthReport,
    SystemHealthStatus,
)
from app.monitoring.system_health_transition import (
    SystemHealthTransitionDetector,
    SystemHealthTransitionType,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def report(
    status: SystemHealthStatus,
    *,
    checked_at: datetime = NOW,
) -> SystemHealthReport:
    reasons = () if status is SystemHealthStatus.HEALTHY else (
        "issue",
    )

    return SystemHealthReport(
        status=status,
        checked_at=checked_at,
        update_health=UpdateHealthReport(
            status=UpdateHealthStatus.HEALTHY,
            checked_at=checked_at,
            reason="healthy",
            latest_run=None,
            latest_success=None,
            consecutive_failure_count=0,
            seconds_since_latest_run=None,
            seconds_since_latest_success=None,
        ),
        runtime_metrics=RuntimeMetricsSnapshot(
            generated_at=checked_at,
            counts={},
        ),
        reasons=reasons,
    )


def test_detects_initial_state() -> None:
    detector = SystemHealthTransitionDetector()

    transition = detector.detect(
        report(SystemHealthStatus.HEALTHY),
        check_number=1,
    )

    assert transition is not None
    assert transition.transition_type is (
        SystemHealthTransitionType.INITIAL
    )


def test_same_status_returns_none() -> None:
    detector = SystemHealthTransitionDetector()
    detector.detect(
        report(SystemHealthStatus.HEALTHY),
        check_number=1,
    )

    transition = detector.detect(
        report(
            SystemHealthStatus.HEALTHY,
            checked_at=NOW + timedelta(seconds=1),
        ),
        check_number=2,
    )

    assert transition is None


def test_detects_degradation_and_recovery() -> None:
    detector = SystemHealthTransitionDetector(
        notify_initial_state=False
    )

    detector.detect(
        report(SystemHealthStatus.HEALTHY),
        check_number=1,
    )

    degraded = detector.detect(
        report(
            SystemHealthStatus.CRITICAL,
            checked_at=NOW + timedelta(seconds=1),
        ),
        check_number=2,
    )
    recovered = detector.detect(
        report(
            SystemHealthStatus.WARNING,
            checked_at=NOW + timedelta(seconds=2),
        ),
        check_number=3,
    )

    assert degraded is not None
    assert degraded.is_degradation
    assert recovered is not None
    assert recovered.is_recovery


def test_rejects_invalid_order() -> None:
    detector = SystemHealthTransitionDetector()
    detector.detect(
        report(SystemHealthStatus.HEALTHY),
        check_number=1,
    )

    with pytest.raises(
        ValueError,
        match="チェック番号",
    ):
        detector.detect(
            report(
                SystemHealthStatus.WARNING,
                checked_at=NOW + timedelta(seconds=1),
            ),
            check_number=1,
        )


def test_reset_clears_previous_state() -> None:
    detector = SystemHealthTransitionDetector()
    detector.detect(
        report(SystemHealthStatus.HEALTHY),
        check_number=1,
    )

    detector.reset()

    assert detector.previous_report is None
