"""自動更新ヘルスチェック状態変化検知のテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.monitoring.update_health_monitor import (
    UpdateHealthMonitorEvent,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)
from app.monitoring.update_health_transition import (
    UpdateHealthTransitionDetector,
    UpdateHealthTransitionType,
)


BASE_TIME = datetime(
    2026,
    7,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)


def create_report(
    status: UpdateHealthStatus,
    *,
    reason: str | None = None,
) -> UpdateHealthReport:
    """状態変化テスト用のヘルスチェック結果を作成する。"""

    return UpdateHealthReport(
        status=status,
        checked_at=BASE_TIME,
        reason=(
            reason
            if reason is not None
            else f"{status.value} reason"
        ),
        latest_run=None,
        latest_success=None,
        consecutive_failure_count=0,
        seconds_since_latest_run=None,
        seconds_since_latest_success=None,
    )


def create_event(
    check_number: int,
    status: UpdateHealthStatus,
    *,
    seconds_after_start: float = 0,
    reason: str | None = None,
) -> UpdateHealthMonitorEvent:
    """状態変化テスト用の監視イベントを作成する。"""

    checked_at = BASE_TIME + timedelta(
        seconds=seconds_after_start,
    )

    report = create_report(
        status,
        reason=reason,
    )

    return UpdateHealthMonitorEvent(
        check_number=check_number,
        checked_at=checked_at,
        report=report,
    )


def test_detector_notifies_initial_state() -> None:
    """既定では最初の状態を通知対象にする。"""

    detector = UpdateHealthTransitionDetector()

    event = create_event(
        1,
        UpdateHealthStatus.HEALTHY,
    )

    transition = detector.detect(
        event
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.INITIAL
    )
    assert transition.previous_status is None
    assert transition.current_status is (
        UpdateHealthStatus.HEALTHY
    )
    assert transition.previous_report is None
    assert transition.current_report == event.report
    assert transition.check_number == 1
    assert transition.detected_at == event.checked_at

    assert transition.is_initial is True
    assert transition.is_degradation is False
    assert transition.is_recovery is False

    assert detector.previous_event == event
    assert detector.previous_status is (
        UpdateHealthStatus.HEALTHY
    )


def test_detector_can_suppress_initial_state() -> None:
    """設定により初回状態通知を抑制する。"""

    detector = UpdateHealthTransitionDetector(
        notify_initial_state=False,
    )

    event = create_event(
        1,
        UpdateHealthStatus.HEALTHY,
    )

    transition = detector.detect(
        event
    )

    assert transition is None
    assert detector.previous_event == event
    assert detector.previous_status is (
        UpdateHealthStatus.HEALTHY
    )


def test_detector_suppresses_same_status() -> None:
    """同じ状態が継続している場合は通知しない。"""

    detector = UpdateHealthTransitionDetector()

    first_transition = detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
        )
    )

    second_transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.HEALTHY,
            seconds_after_start=60,
        )
    )

    assert first_transition is not None
    assert second_transition is None
    assert detector.previous_status is (
        UpdateHealthStatus.HEALTHY
    )
    assert detector.previous_event is not None
    assert detector.previous_event.check_number == 2


def test_detector_detects_healthy_to_warning_degradation() -> None:
    """HEALTHYからWARNINGへの悪化を検出する。"""

    detector = UpdateHealthTransitionDetector()

    first_event = create_event(
        1,
        UpdateHealthStatus.HEALTHY,
    )
    second_event = create_event(
        2,
        UpdateHealthStatus.WARNING,
        seconds_after_start=60,
    )

    detector.detect(
        first_event
    )

    transition = detector.detect(
        second_event
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.DEGRADED
    )
    assert transition.previous_status is (
        UpdateHealthStatus.HEALTHY
    )
    assert transition.current_status is (
        UpdateHealthStatus.WARNING
    )
    assert transition.previous_report == (
        first_event.report
    )
    assert transition.current_report == (
        second_event.report
    )
    assert transition.is_degradation is True
    assert transition.is_recovery is False


def test_detector_detects_warning_to_error_degradation() -> None:
    """WARNINGからERRORへの悪化を検出する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.WARNING,
        )
    )

    transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.ERROR,
            seconds_after_start=60,
        )
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.DEGRADED
    )
    assert transition.previous_status is (
        UpdateHealthStatus.WARNING
    )
    assert transition.current_status is (
        UpdateHealthStatus.ERROR
    )


def test_detector_detects_healthy_to_error_degradation() -> None:
    """HEALTHYからERRORへの直接悪化を検出する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
        )
    )

    transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.ERROR,
            seconds_after_start=60,
        )
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.DEGRADED
    )
    assert transition.is_degradation is True


def test_detector_detects_error_to_warning_recovery() -> None:
    """ERRORからWARNINGへの改善を検出する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.ERROR,
        )
    )

    transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.WARNING,
            seconds_after_start=60,
        )
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.RECOVERED
    )
    assert transition.previous_status is (
        UpdateHealthStatus.ERROR
    )
    assert transition.current_status is (
        UpdateHealthStatus.WARNING
    )
    assert transition.is_recovery is True
    assert transition.is_degradation is False


def test_detector_detects_warning_to_healthy_recovery() -> None:
    """WARNINGからHEALTHYへの復旧を検出する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.WARNING,
        )
    )

    transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.HEALTHY,
            seconds_after_start=60,
        )
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.RECOVERED
    )
    assert transition.current_status is (
        UpdateHealthStatus.HEALTHY
    )
    assert transition.is_recovery is True


def test_detector_detects_error_to_healthy_recovery() -> None:
    """ERRORからHEALTHYへの直接復旧を検出する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.ERROR,
        )
    )

    transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.HEALTHY,
            seconds_after_start=60,
        )
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.RECOVERED
    )
    assert transition.previous_status is (
        UpdateHealthStatus.ERROR
    )
    assert transition.current_status is (
        UpdateHealthStatus.HEALTHY
    )


def test_detector_tracks_multiple_transitions() -> None:
    """複数回の状態変化を順番に検出する。"""

    detector = UpdateHealthTransitionDetector()

    transitions = [
        detector.detect(
            create_event(
                1,
                UpdateHealthStatus.HEALTHY,
            )
        ),
        detector.detect(
            create_event(
                2,
                UpdateHealthStatus.HEALTHY,
                seconds_after_start=60,
            )
        ),
        detector.detect(
            create_event(
                3,
                UpdateHealthStatus.WARNING,
                seconds_after_start=120,
            )
        ),
        detector.detect(
            create_event(
                4,
                UpdateHealthStatus.WARNING,
                seconds_after_start=180,
            )
        ),
        detector.detect(
            create_event(
                5,
                UpdateHealthStatus.ERROR,
                seconds_after_start=240,
            )
        ),
        detector.detect(
            create_event(
                6,
                UpdateHealthStatus.HEALTHY,
                seconds_after_start=300,
            )
        ),
    ]

    notified_transitions = [
        transition
        for transition in transitions
        if transition is not None
    ]

    assert [
        transition.transition_type
        for transition in notified_transitions
    ] == [
        UpdateHealthTransitionType.INITIAL,
        UpdateHealthTransitionType.DEGRADED,
        UpdateHealthTransitionType.DEGRADED,
        UpdateHealthTransitionType.RECOVERED,
    ]

    assert [
        transition.current_status
        for transition in notified_transitions
    ] == [
        UpdateHealthStatus.HEALTHY,
        UpdateHealthStatus.WARNING,
        UpdateHealthStatus.ERROR,
        UpdateHealthStatus.HEALTHY,
    ]


def test_transition_message_contains_statuses_and_reason() -> None:
    """通知メッセージに状態変化と理由を含める。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
        )
    )

    transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.ERROR,
            seconds_after_start=60,
            reason="database unavailable",
        )
    )

    assert transition is not None

    message = transition.message

    assert "degraded" in message
    assert "previous=healthy" in message
    assert "current=error" in message
    assert "check_number=2" in message
    assert "database unavailable" in message


def test_detector_reset_forgets_previous_state() -> None:
    """リセット後は次のイベントを初回として扱う。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
        )
    )

    detector.reset()

    assert detector.previous_event is None
    assert detector.previous_status is None

    transition = detector.detect(
        create_event(
            1,
            UpdateHealthStatus.ERROR,
        )
    )

    assert transition is not None
    assert transition.transition_type is (
        UpdateHealthTransitionType.INITIAL
    )
    assert transition.previous_status is None
    assert transition.current_status is (
        UpdateHealthStatus.ERROR
    )


def test_detector_updates_state_when_initial_notification_is_suppressed() -> None:
    """初回通知を抑制しても次回比較用状態は保持する。"""

    detector = UpdateHealthTransitionDetector(
        notify_initial_state=False,
    )

    first_transition = detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
        )
    )

    second_transition = detector.detect(
        create_event(
            2,
            UpdateHealthStatus.WARNING,
            seconds_after_start=60,
        )
    )

    assert first_transition is None
    assert second_transition is not None
    assert second_transition.transition_type is (
        UpdateHealthTransitionType.DEGRADED
    )
    assert second_transition.previous_status is (
        UpdateHealthStatus.HEALTHY
    )


def test_detector_rejects_non_positive_check_number() -> None:
    """0以下のチェック番号を拒否する。"""

    detector = UpdateHealthTransitionDetector()

    with pytest.raises(
        ValueError,
        match="チェック番号",
    ):
        detector.detect(
            create_event(
                0,
                UpdateHealthStatus.HEALTHY,
            )
        )


def test_detector_rejects_duplicate_check_number() -> None:
    """前回と同じチェック番号を拒否する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
        )
    )

    with pytest.raises(
        ValueError,
        match="前回より大きい",
    ):
        detector.detect(
            create_event(
                1,
                UpdateHealthStatus.WARNING,
                seconds_after_start=60,
            )
        )


def test_detector_rejects_decreasing_check_number() -> None:
    """前回より小さいチェック番号を拒否する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            2,
            UpdateHealthStatus.HEALTHY,
        )
    )

    with pytest.raises(
        ValueError,
        match="前回より大きい",
    ):
        detector.detect(
            create_event(
                1,
                UpdateHealthStatus.WARNING,
                seconds_after_start=60,
            )
        )


def test_detector_rejects_event_time_before_previous_event() -> None:
    """前回より過去の確認日時を拒否する。"""

    detector = UpdateHealthTransitionDetector()

    detector.detect(
        create_event(
            1,
            UpdateHealthStatus.HEALTHY,
            seconds_after_start=60,
        )
    )

    with pytest.raises(
        ValueError,
        match="前回以後",
    ):
        detector.detect(
            create_event(
                2,
                UpdateHealthStatus.WARNING,
                seconds_after_start=30,
            )
        )