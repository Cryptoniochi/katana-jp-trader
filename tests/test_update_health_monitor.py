"""自動更新ヘルスチェック監視ループのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.monitoring.update_health_monitor import (
    MonitorStopReason,
    UpdateHealthMonitor,
    UpdateHealthMonitorError,
    UpdateHealthMonitorEvent,
    UpdateHealthMonitorPolicy,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


BASE_TIME = datetime(
    2026,
    7,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)


class MutableClock:
    """テスト用の変更可能な時計。"""

    def __init__(
        self,
        current_time: datetime,
    ) -> None:
        """初期日時を設定する。"""

        self.current_time = current_time

    def now(self) -> datetime:
        """現在日時を返す。"""

        return self.current_time

    def advance(
        self,
        seconds: float,
    ) -> None:
        """時計を指定秒数進める。"""

        self.current_time += timedelta(
            seconds=seconds
        )


class FakeHealthChecker:
    """設定済み結果を順番に返すヘルスチェッカー。"""

    def __init__(
        self,
        outcomes: list[
            UpdateHealthReport | Exception
        ],
    ) -> None:
        """返却結果または例外を設定する。"""

        self.outcomes = iter(outcomes)
        self.call_count = 0

    def check(self) -> UpdateHealthReport:
        """次の結果を返すか例外を送出する。"""

        self.call_count += 1
        outcome = next(self.outcomes)

        if isinstance(
            outcome,
            Exception,
        ):
            raise outcome

        return outcome


def create_report(
    status: UpdateHealthStatus,
) -> UpdateHealthReport:
    """最低限のヘルスチェック結果を作成する。"""

    return UpdateHealthReport(
        status=status,
        checked_at=BASE_TIME,
        reason=f"{status.value} reason",
        latest_run=None,
        latest_success=None,
        consecutive_failure_count=0,
        seconds_since_latest_run=None,
        seconds_since_latest_success=None,
    )


def create_monitor(
    checker: FakeHealthChecker,
    clock: MutableClock,
    *,
    policy: UpdateHealthMonitorPolicy | None = None,
    events: list[UpdateHealthMonitorEvent] | None = None,
    errors: list[UpdateHealthMonitorError] | None = None,
    sleep_calls: list[float] | None = None,
) -> UpdateHealthMonitor:
    """テスト用の監視ループを作成する。"""

    resolved_events = (
        events
        if events is not None
        else []
    )
    resolved_errors = (
        errors
        if errors is not None
        else []
    )
    resolved_sleep_calls = (
        sleep_calls
        if sleep_calls is not None
        else []
    )

    def sleeper(
        seconds: float,
    ) -> None:
        resolved_sleep_calls.append(
            seconds
        )
        clock.advance(
            seconds
        )

    return UpdateHealthMonitor(
        checker=checker,
        policy=policy,
        sleeper=sleeper,
        now_provider=clock.now,
        event_callback=resolved_events.append,
        error_callback=resolved_errors.append,
    )


def test_monitor_runs_until_maximum_check_count() -> None:
    """指定回数だけヘルスチェックを実行する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.WARNING
            ),
            create_report(
                UpdateHealthStatus.ERROR
            ),
        ]
    )

    events: list[
        UpdateHealthMonitorEvent
    ] = []
    sleep_calls: list[float] = []

    monitor = create_monitor(
        checker,
        clock,
        events=events,
        sleep_calls=sleep_calls,
        policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=10,
        ),
    )

    result = monitor.run(
        max_checks=3
    )

    assert result.stop_reason is (
        MonitorStopReason.MAX_CHECKS_REACHED
    )
    assert result.completed_normally is True
    assert result.check_count == 3
    assert result.successful_check_count == 3
    assert result.failed_check_count == 0
    assert result.consecutive_error_count == 0

    assert checker.call_count == 3
    assert sleep_calls == [
        10,
        10,
    ]

    assert [
        event.status
        for event in events
    ] == [
        UpdateHealthStatus.HEALTHY,
        UpdateHealthStatus.WARNING,
        UpdateHealthStatus.ERROR,
    ]

    assert result.latest_event == events[-1]
    assert result.latest_error is None
    assert result.duration_seconds == (
        pytest.approx(20)
    )


def test_monitor_stops_before_first_check() -> None:
    """開始時点で停止要求があればチェックしない。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            )
        ]
    )

    monitor = create_monitor(
        checker,
        clock,
    )

    result = monitor.run(
        stop_requested=lambda: True,
    )

    assert result.stop_reason is (
        MonitorStopReason.STOP_REQUESTED
    )
    assert result.check_count == 0
    assert result.successful_check_count == 0
    assert result.failed_check_count == 0
    assert checker.call_count == 0


def test_monitor_stops_after_external_request() -> None:
    """外部停止要求を検出して監視を終了する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
        ]
    )

    stop_checks = iter(
        [
            False,
            False,
            True,
        ]
    )

    monitor = create_monitor(
        checker,
        clock,
        policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=5,
        ),
    )

    result = monitor.run(
        stop_requested=lambda: next(
            stop_checks
        ),
    )

    assert result.stop_reason is (
        MonitorStopReason.STOP_REQUESTED
    )
    assert result.check_count == 1
    assert checker.call_count == 1


def test_monitor_continues_after_temporary_check_error() -> None:
    """一時的なチェック例外後も監視を継続する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            RuntimeError(
                "temporary failure"
            ),
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
        ]
    )

    events: list[
        UpdateHealthMonitorEvent
    ] = []
    errors: list[
        UpdateHealthMonitorError
    ] = []

    monitor = create_monitor(
        checker,
        clock,
        events=events,
        errors=errors,
        policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=1,
            continue_on_check_error=True,
            maximum_consecutive_check_errors=3,
        ),
    )

    result = monitor.run(
        max_checks=2
    )

    assert result.stop_reason is (
        MonitorStopReason.MAX_CHECKS_REACHED
    )
    assert result.check_count == 2
    assert result.successful_check_count == 1
    assert result.failed_check_count == 1
    assert result.consecutive_error_count == 0

    assert len(errors) == 1
    assert errors[0].check_number == 1
    assert errors[0].consecutive_error_count == 1
    assert str(errors[0].error) == (
        "temporary failure"
    )

    assert len(events) == 1
    assert events[0].check_number == 2

    assert result.latest_event == events[0]
    assert result.latest_error == errors[0]


def test_monitor_stops_immediately_when_error_continuation_disabled() -> None:
    """例外継続無効なら最初のチェック失敗で終了する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            RuntimeError(
                "check failure"
            )
        ]
    )

    monitor = create_monitor(
        checker,
        clock,
        policy=UpdateHealthMonitorPolicy(
            continue_on_check_error=False,
        ),
    )

    result = monitor.run(
        max_checks=5
    )

    assert result.stop_reason is (
        MonitorStopReason.CHECK_FAILED
    )
    assert result.completed_normally is False
    assert result.check_count == 1
    assert result.successful_check_count == 0
    assert result.failed_check_count == 1
    assert result.consecutive_error_count == 1
    assert checker.call_count == 1


def test_monitor_stops_at_consecutive_error_threshold() -> None:
    """連続チェックエラーが上限に達したら終了する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            RuntimeError(
                "failure 1"
            ),
            RuntimeError(
                "failure 2"
            ),
            RuntimeError(
                "failure 3"
            ),
        ]
    )

    errors: list[
        UpdateHealthMonitorError
    ] = []

    monitor = create_monitor(
        checker,
        clock,
        errors=errors,
        policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=2,
            continue_on_check_error=True,
            maximum_consecutive_check_errors=3,
        ),
    )

    result = monitor.run(
        max_checks=10
    )

    assert result.stop_reason is (
        MonitorStopReason.CHECK_FAILED
    )
    assert result.check_count == 3
    assert result.failed_check_count == 3
    assert result.consecutive_error_count == 3
    assert checker.call_count == 3

    assert [
        error.consecutive_error_count
        for error in errors
    ] == [
        1,
        2,
        3,
    ]

    assert result.latest_error == errors[-1]


def test_success_resets_consecutive_check_error_count() -> None:
    """成功チェックで連続例外数をリセットする。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            RuntimeError(
                "failure 1"
            ),
            RuntimeError(
                "failure 2"
            ),
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            RuntimeError(
                "failure 3"
            ),
        ]
    )

    errors: list[
        UpdateHealthMonitorError
    ] = []

    monitor = create_monitor(
        checker,
        clock,
        errors=errors,
        policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
            maximum_consecutive_check_errors=3,
        ),
    )

    result = monitor.run(
        max_checks=4
    )

    assert result.stop_reason is (
        MonitorStopReason.MAX_CHECKS_REACHED
    )
    assert result.successful_check_count == 1
    assert result.failed_check_count == 3
    assert result.consecutive_error_count == 1

    assert [
        error.consecutive_error_count
        for error in errors
    ] == [
        1,
        2,
        1,
    ]


def test_monitor_passes_event_sequence_numbers() -> None:
    """イベントへ通算チェック番号を設定する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.WARNING
            ),
        ]
    )

    events: list[
        UpdateHealthMonitorEvent
    ] = []

    monitor = create_monitor(
        checker,
        clock,
        events=events,
        policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
    )

    monitor.run(
        max_checks=2
    )

    assert [
        event.check_number
        for event in events
    ] == [
        1,
        2,
    ]


def test_monitor_rejects_naive_current_time() -> None:
    """タイムゾーンなしの現在日時を拒否する。"""

    checker = FakeHealthChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            )
        ]
    )

    monitor = UpdateHealthMonitor(
        checker,
        now_provider=lambda: datetime(
            2026,
            7,
            16,
            12,
            0,
        ),
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        monitor.run(
            max_checks=1
        )


def test_monitor_rejects_invalid_max_checks() -> None:
    """0以下の最大チェック回数を拒否する。"""

    clock = MutableClock(
        BASE_TIME
    )
    checker = FakeHealthChecker([])

    monitor = create_monitor(
        checker,
        clock,
    )

    with pytest.raises(
        ValueError,
        match="最大チェック回数",
    ):
        monitor.run(
            max_checks=0
        )


@pytest.mark.parametrize(
    (
        "policy_arguments",
        "message",
    ),
    [
        (
            {
                "check_interval_seconds": -1,
            },
            "監視間隔",
        ),
        (
            {
                "maximum_consecutive_check_errors": 0,
            },
            "最大連続チェックエラー回数",
        ),
    ],
)
def test_monitor_policy_rejects_invalid_values(
    policy_arguments: dict[str, int],
    message: str,
) -> None:
    """不正な監視条件を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        UpdateHealthMonitorPolicy(
            **policy_arguments,
        )