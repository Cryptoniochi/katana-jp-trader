"""自動更新ヘルスチェック常駐監視CLIのテスト。"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.monitor_update_health import (
    EXIT_MONITOR_FAILED,
    EXIT_SUCCESS,
    MonitoringSessionResult,
    SignalStopController,
    configure_logger_level,
    create_health_policy,
    create_monitor_policy,
    determine_exit_code,
    format_monitor_summary,
    format_transition,
    parse_arguments,
    run_monitoring_session,
)
from app.monitoring.update_health_monitor import (
    MonitorStopReason,
    UpdateHealthMonitorPolicy,
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
        """現在日時を指定秒数進める。"""

        self.current_time += timedelta(
            seconds=seconds
        )


class FakeChecker:
    """設定済み結果を順番に返すチェッカー。"""

    def __init__(
        self,
        outcomes: list[
            UpdateHealthReport | Exception
        ],
    ) -> None:
        """チェック結果または例外を設定する。"""

        self.outcomes = iter(
            outcomes
        )
        self.call_count = 0

    def check(
        self,
    ) -> UpdateHealthReport:
        """次の結果を返すか例外を送出する。"""

        self.call_count += 1

        outcome = next(
            self.outcomes
        )

        if isinstance(
            outcome,
            Exception,
        ):
            raise outcome

        return outcome


def create_report(
    status: UpdateHealthStatus,
    *,
    reason: str | None = None,
) -> UpdateHealthReport:
    """テスト用ヘルスチェック結果を作成する。"""

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


def create_sleeper(
    clock: MutableClock,
    calls: list[float],
) -> callable:
    """呼出履歴を保存して時計を進めるsleep処理を作成する。"""

    def sleeper(
        seconds: float,
    ) -> None:
        calls.append(
            seconds
        )
        clock.advance(
            seconds
        )

    return sleeper


def test_parse_arguments_reads_monitor_options(
    tmp_path: Path,
) -> None:
    """常駐監視CLIの引数を読み込む。"""

    database_path = (
        tmp_path / "katana.db"
    )

    arguments = parse_arguments(
        [
            "--database",
            str(database_path),
            "--interval-seconds",
            "30",
            "--max-checks",
            "5",
            "--maximum-check-errors",
            "4",
            "--stop-on-check-error",
            "--suppress-initial",
            "--history-limit",
            "50",
            "--warning-failures",
            "3",
            "--error-failures",
            "6",
            "--warning-stale-seconds",
            "1000",
            "--error-stale-seconds",
            "2000",
            "--running-timeout-seconds",
            "300",
            "--log-level",
            "DEBUG",
            "--quiet",
        ]
    )

    assert arguments.database == database_path
    assert arguments.interval_seconds == 30
    assert arguments.max_checks == 5
    assert arguments.maximum_check_errors == 4
    assert arguments.stop_on_check_error is True
    assert arguments.suppress_initial is True
    assert arguments.history_limit == 50
    assert arguments.warning_failures == 3
    assert arguments.error_failures == 6
    assert arguments.warning_stale_seconds == 1000
    assert arguments.error_stale_seconds == 2000
    assert arguments.running_timeout_seconds == 300
    assert arguments.log_level == "DEBUG"
    assert arguments.quiet is True


def test_create_health_policy_from_arguments() -> None:
    """CLI引数からヘルスチェック条件を作成する。"""

    arguments = parse_arguments(
        [
            "--history-limit",
            "50",
            "--warning-failures",
            "3",
            "--error-failures",
            "6",
            "--warning-stale-seconds",
            "1000",
            "--error-stale-seconds",
            "2000",
            "--running-timeout-seconds",
            "300",
        ]
    )

    policy = create_health_policy(
        arguments
    )

    assert policy.history_limit == 50
    assert policy.warning_failure_count == 3
    assert policy.error_failure_count == 6
    assert policy.warning_stale_seconds == 1000
    assert policy.error_stale_seconds == 2000
    assert policy.running_timeout_seconds == 300


def test_create_monitor_policy_from_arguments() -> None:
    """CLI引数から監視ループ条件を作成する。"""

    arguments = parse_arguments(
        [
            "--interval-seconds",
            "15",
            "--maximum-check-errors",
            "4",
            "--stop-on-check-error",
        ]
    )

    policy = create_monitor_policy(
        arguments
    )

    assert policy.check_interval_seconds == 15
    assert policy.maximum_consecutive_check_errors == 4
    assert policy.continue_on_check_error is False


def test_monitoring_session_suppresses_unchanged_status() -> None:
    """状態が同じ間は通知対象を増やさない。"""

    clock = MutableClock(
        BASE_TIME
    )
    sleep_calls: list[float] = []

    checker = FakeChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.WARNING
            ),
            create_report(
                UpdateHealthStatus.WARNING
            ),
            create_report(
                UpdateHealthStatus.ERROR
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=10,
            )
        ),
        sleeper=create_sleeper(
            clock,
            sleep_calls,
        ),
        now_provider=clock.now,
        max_checks=5,
    )

    assert result.monitor_result.check_count == 5
    assert len(
        result.events
    ) == 5
    assert len(
        result.errors
    ) == 0

    assert [
        transition.transition_type
        for transition in result.transitions
    ] == [
        UpdateHealthTransitionType.INITIAL,
        UpdateHealthTransitionType.DEGRADED,
        UpdateHealthTransitionType.DEGRADED,
    ]

    assert [
        transition.current_status
        for transition in result.transitions
    ] == [
        UpdateHealthStatus.HEALTHY,
        UpdateHealthStatus.WARNING,
        UpdateHealthStatus.ERROR,
    ]

    assert result.healthy_check_count == 2
    assert result.warning_check_count == 2
    assert result.error_check_count == 1
    assert result.transition_count == 3
    assert sleep_calls == [
        10,
        10,
        10,
        10,
    ]


def test_monitoring_session_detects_recovery() -> None:
    """ERRORからHEALTHYへの復旧を検出する。"""

    clock = MutableClock(
        BASE_TIME
    )

    checker = FakeChecker(
        [
            create_report(
                UpdateHealthStatus.ERROR
            ),
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    assert result.transition_count == 2

    recovery = result.transitions[-1]

    assert recovery.transition_type is (
        UpdateHealthTransitionType.RECOVERED
    )
    assert recovery.previous_status is (
        UpdateHealthStatus.ERROR
    )
    assert recovery.current_status is (
        UpdateHealthStatus.HEALTHY
    )


def test_monitoring_session_can_suppress_initial_transition() -> None:
    """設定により初回状態通知を抑制する。"""

    clock = MutableClock(
        BASE_TIME
    )

    checker = FakeChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.WARNING
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
            )
        ),
        transition_detector=(
            UpdateHealthTransitionDetector(
                notify_initial_state=False,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    assert result.transition_count == 1
    assert (
        result.transitions[0]
        .transition_type
        is UpdateHealthTransitionType.DEGRADED
    )


def test_monitoring_session_calls_transition_callback() -> None:
    """検出した状態変化をコールバックへ渡す。"""

    clock = MutableClock(
        BASE_TIME
    )
    transitions = []

    checker = FakeChecker(
        [
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
            create_report(
                UpdateHealthStatus.ERROR
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
        transition_callback=(
            transitions.append
        ),
    )

    assert tuple(
        transitions
    ) == result.transitions


def test_monitoring_session_collects_check_errors() -> None:
    """ヘルスチェック例外を監視結果へ保存する。"""

    clock = MutableClock(
        BASE_TIME
    )
    callback_errors = []

    checker = FakeChecker(
        [
            RuntimeError(
                "temporary error"
            ),
            create_report(
                UpdateHealthStatus.HEALTHY
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
                maximum_consecutive_check_errors=3,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
        error_callback=(
            callback_errors.append
        ),
    )

    assert len(
        result.errors
    ) == 1
    assert tuple(
        callback_errors
    ) == result.errors
    assert str(
        result.errors[0].error
    ) == "temporary error"

    assert result.monitor_result.stop_reason is (
        MonitorStopReason.MAX_CHECKS_REACHED
    )


def test_monitoring_session_stops_after_check_error_threshold() -> None:
    """連続チェックエラー上限で監視を終了する。"""

    clock = MutableClock(
        BASE_TIME
    )

    checker = FakeChecker(
        [
            RuntimeError(
                "failure 1"
            ),
            RuntimeError(
                "failure 2"
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
                maximum_consecutive_check_errors=2,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=10,
    )

    assert result.monitor_result.stop_reason is (
        MonitorStopReason.CHECK_FAILED
    )
    assert result.monitor_result.check_count == 2
    assert len(
        result.errors
    ) == 2

    assert determine_exit_code(
        result
    ) == EXIT_MONITOR_FAILED


def test_determine_exit_code_returns_success_for_normal_stop() -> None:
    """正常な回数上限終了では成功コードを返す。"""

    clock = MutableClock(
        BASE_TIME
    )

    result = run_monitoring_session(
        checker=FakeChecker(
            [
                create_report(
                    UpdateHealthStatus.HEALTHY
                )
            ]
        ),
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=1,
    )

    assert determine_exit_code(
        result
    ) == EXIT_SUCCESS


def test_format_transition_contains_state_change() -> None:
    """状態変化表示に主要情報を含める。"""

    clock = MutableClock(
        BASE_TIME
    )

    result = run_monitoring_session(
        checker=FakeChecker(
            [
                create_report(
                    UpdateHealthStatus.HEALTHY
                ),
                create_report(
                    UpdateHealthStatus.ERROR,
                    reason="database unavailable",
                ),
            ]
        ),
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    message = format_transition(
        result.transitions[-1]
    )

    assert "degraded" in message
    assert "healthy" in message
    assert "error" in message
    assert "database unavailable" in message


def test_format_monitor_summary_contains_counts() -> None:
    """終了サマリーにチェック件数と状態件数を含める。"""

    clock = MutableClock(
        BASE_TIME
    )

    result = run_monitoring_session(
        checker=FakeChecker(
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
        ),
        monitor_policy=(
            UpdateHealthMonitorPolicy(
                check_interval_seconds=0,
            )
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=3,
    )

    message = format_monitor_summary(
        result
    )

    assert "Update Health Monitor Summary" in message
    assert "Checks                  : 3" in message
    assert "Healthy results         : 1" in message
    assert "Warning results         : 1" in message
    assert "Error results           : 1" in message
    assert "State transitions       : 3" in message


def test_configure_logger_level() -> None:
    """LoggerとHandlerのレベルを変更する。"""

    logger = logging.getLogger(
        "test-monitor-logger"
    )
    logger.handlers.clear()

    handler = logging.StreamHandler()
    logger.addHandler(
        handler
    )

    configure_logger_level(
        logger,
        "WARNING",
    )

    assert logger.level == logging.WARNING
    assert handler.level == logging.WARNING


def test_configure_logger_level_rejects_unknown_level() -> None:
    """未対応のログレベルを拒否する。"""

    logger = logging.getLogger(
        "test-invalid-monitor-logger"
    )

    with pytest.raises(
        ValueError,
        match="未対応",
    ):
        configure_logger_level(
            logger,
            "TRACE",
        )


def test_signal_stop_controller_sets_stop_request() -> None:
    """明示的な停止要求を保持する。"""

    controller = SignalStopController()

    assert controller.is_stop_requested is False
    assert controller.stop_requested() is False

    controller.request_stop()

    assert controller.is_stop_requested is True
    assert controller.stop_requested() is True