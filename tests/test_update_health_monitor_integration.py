"""自動更新実行履歴・ヘルス判定・常駐監視の統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import initialize_database
from app.monitor_update_health import (
    EXIT_MONITOR_FAILED,
    EXIT_SUCCESS,
    determine_exit_code,
    format_monitor_summary,
    format_transition,
    run_monitoring_session,
)
from app.monitoring.update_health_monitor import (
    MonitorStopReason,
    UpdateHealthMonitorPolicy,
)
from app.monitoring.update_health_service import (
    UpdateHealthPolicy,
    UpdateHealthService,
    UpdateHealthStatus,
)
from app.monitoring.update_health_transition import (
    UpdateHealthTransitionDetector,
    UpdateHealthTransitionType,
)
from app.monitoring.update_run_repository import (
    UpdateRunMetrics,
    UpdateRunRepository,
    UpdateRunStatus,
)


BASE_TIME = datetime(
    2026,
    7,
    16,
    9,
    0,
    tzinfo=timezone.utc,
)


class MutableClock:
    """テスト内で現在日時を変更できる時計。"""

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
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
    ) -> datetime:
        """時計を指定時間だけ進める。"""

        self.current_time += timedelta(
            seconds=seconds,
            minutes=minutes,
            hours=hours,
        )

        return self.current_time


class SequentialRunIdProvider:
    """連番の実行IDを生成する。"""

    def __init__(self) -> None:
        """連番を初期化する。"""

        self.next_number = 1

    def __call__(self) -> str:
        """次の実行IDを返す。"""

        run_id = f"run-{self.next_number:03d}"
        self.next_number += 1

        return run_id


class SequenceChecker:
    """指定した処理をチェックごとに実行する。"""

    def __init__(
        self,
        actions: list[callable],
    ) -> None:
        """チェック時に実行する処理を設定する。"""

        self.actions = iter(actions)
        self.call_count = 0

    def check(self):
        """次の処理を実行して結果を返す。"""

        self.call_count += 1
        action = next(self.actions)

        return action()


def create_repository(
    tmp_path: Path,
    clock: MutableClock,
) -> UpdateRunRepository:
    """初期化済み実行履歴Repositoryを作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    return UpdateRunRepository(
        database_path,
        now_provider=clock.now,
        run_id_provider=SequentialRunIdProvider(),
    )


def create_health_service(
    repository: UpdateRunRepository,
    clock: MutableClock,
    *,
    policy: UpdateHealthPolicy | None = None,
) -> UpdateHealthService:
    """実DBを使用するヘルスチェックサービスを作成する。"""

    return UpdateHealthService(
        repository=repository,
        policy=policy,
        now_provider=clock.now,
    )


def create_success_metrics(
    *,
    requested_code_count: int = 2,
    updated_code_count: int = 2,
    skipped_code_count: int = 0,
) -> UpdateRunMetrics:
    """正常終了用の件数情報を作成する。"""

    return UpdateRunMetrics(
        requested_code_count=requested_code_count,
        updated_code_count=updated_code_count,
        skipped_code_count=skipped_code_count,
        failed_code_count=0,
        business_date_count=2,
        request_count=2,
        successful_request_count=2,
        empty_request_count=0,
        failed_request_count=0,
        processed_bar_count=120,
    )


def create_failure_metrics(
    *,
    requested_code_count: int = 1,
) -> UpdateRunMetrics:
    """完全失敗用の件数情報を作成する。"""

    return UpdateRunMetrics(
        requested_code_count=requested_code_count,
        updated_code_count=0,
        skipped_code_count=0,
        failed_code_count=requested_code_count,
        business_date_count=1,
        request_count=1,
        successful_request_count=0,
        empty_request_count=0,
        failed_request_count=1,
        processed_bar_count=0,
    )


def create_partial_failure_metrics() -> UpdateRunMetrics:
    """部分失敗用の件数情報を作成する。"""

    return UpdateRunMetrics(
        requested_code_count=2,
        updated_code_count=1,
        skipped_code_count=0,
        failed_code_count=1,
        business_date_count=2,
        request_count=2,
        successful_request_count=1,
        empty_request_count=0,
        failed_request_count=1,
        processed_bar_count=60,
    )


def start_and_finish_run(
    repository: UpdateRunRepository,
    clock: MutableClock,
    *,
    status: UpdateRunStatus,
    exit_code: int,
    metrics: UpdateRunMetrics,
    error_message: str | None = None,
    duration_seconds: float = 1,
) -> str:
    """実行履歴を開始し、指定状態で終了する。"""

    started = repository.start(
        process_name="jquants-incremental-update",
        requested_code_count=(
            metrics.requested_code_count
        ),
    )

    clock.advance(
        seconds=duration_seconds,
    )

    repository.finish(
        started.run_id,
        status=status,
        exit_code=exit_code,
        metrics=metrics,
        error_message=error_message,
    )

    return started.run_id


def create_monitor_sleeper(
    clock: MutableClock,
    sleep_calls: list[float],
) -> callable:
    """時計を進める監視用sleep処理を作成する。"""

    def sleeper(
        seconds: float,
    ) -> None:
        sleep_calls.append(
            seconds,
        )

        clock.advance(
            seconds=seconds,
        )

    return sleeper


def test_monitor_detects_initial_healthy_state_from_real_database(
    tmp_path: Path,
) -> None:
    """実DBの成功履歴から初回HEALTHY通知を生成する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    run_id = start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    result = run_monitoring_session(
        checker=health_service,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=1,
    )

    assert result.monitor_result.stop_reason is (
        MonitorStopReason.MAX_CHECKS_REACHED
    )
    assert result.monitor_result.check_count == 1
    assert result.monitor_result.successful_check_count == 1
    assert result.monitor_result.failed_check_count == 0

    assert result.healthy_check_count == 1
    assert result.warning_check_count == 0
    assert result.error_check_count == 0

    assert result.transition_count == 1

    transition = result.transitions[0]

    assert transition.transition_type is (
        UpdateHealthTransitionType.INITIAL
    )
    assert transition.current_status is (
        UpdateHealthStatus.HEALTHY
    )
    assert transition.current_report.latest_run is not None
    assert (
        transition.current_report.latest_run.run_id
        == run_id
    )

    assert determine_exit_code(
        result,
    ) == EXIT_SUCCESS


def test_monitor_suppresses_repeated_healthy_state(
    tmp_path: Path,
) -> None:
    """実DBの状態が変わらなければ通知を増やさない。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    sleep_calls: list[float] = []

    result = run_monitoring_session(
        checker=health_service,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=10,
        ),
        sleeper=create_monitor_sleeper(
            clock,
            sleep_calls,
        ),
        now_provider=clock.now,
        max_checks=3,
    )

    assert result.monitor_result.check_count == 3
    assert result.healthy_check_count == 3
    assert result.transition_count == 1

    assert result.transitions[0].transition_type is (
        UpdateHealthTransitionType.INITIAL
    )

    assert sleep_calls == [
        10,
        10,
    ]


def test_monitor_detects_success_to_failure_degradation(
    tmp_path: Path,
) -> None:
    """監視中に失敗履歴が追加されると悪化通知を生成する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    success_run_id = start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    def first_check():
        return health_service.check()

    def second_check():
        clock.advance(
            minutes=1,
        )

        failure_run_id = start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=create_failure_metrics(),
            error_message="calendar unavailable",
        )

        report = health_service.check()

        assert report.latest_run is not None
        assert report.latest_run.run_id == failure_run_id

        return report

    checker = SequenceChecker(
        [
            first_check,
            second_check,
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    assert result.transition_count == 2

    initial = result.transitions[0]
    degraded = result.transitions[1]

    assert initial.current_report.latest_run is not None
    assert (
        initial.current_report.latest_run.run_id
        == success_run_id
    )

    assert degraded.transition_type is (
        UpdateHealthTransitionType.DEGRADED
    )
    assert degraded.previous_status is (
        UpdateHealthStatus.HEALTHY
    )
    assert degraded.current_status is (
        UpdateHealthStatus.WARNING
    )
    assert "calendar unavailable" in (
        degraded.current_report
        .latest_run.error_message
    )


def test_monitor_detects_partial_failure_as_warning(
    tmp_path: Path,
) -> None:
    """部分失敗履歴をWARNINGへの悪化として検出する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    def healthy_check():
        return health_service.check()

    def partial_failure_check():
        clock.advance(
            minutes=1,
        )

        start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.PARTIAL_FAILURE,
            exit_code=1,
            metrics=create_partial_failure_metrics(),
            error_message="one request failed",
        )

        return health_service.check()

    result = run_monitoring_session(
        checker=SequenceChecker(
            [
                healthy_check,
                partial_failure_check,
            ]
        ),
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    assert result.healthy_check_count == 1
    assert result.warning_check_count == 1
    assert result.error_check_count == 0

    transition = result.transitions[-1]

    assert transition.transition_type is (
        UpdateHealthTransitionType.DEGRADED
    )
    assert transition.current_status is (
        UpdateHealthStatus.WARNING
    )


def test_monitor_detects_warning_to_error_after_failure_threshold(
    tmp_path: Path,
) -> None:
    """連続失敗が閾値に達するとWARNINGからERRORへ遷移する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    policy = UpdateHealthPolicy(
        warning_failure_count=1,
        error_failure_count=2,
    )

    health_service = create_health_service(
        repository,
        clock,
        policy=policy,
    )

    def healthy_check():
        return health_service.check()

    def first_failure_check():
        clock.advance(
            minutes=1,
        )

        start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=create_failure_metrics(),
            error_message="failure 1",
        )

        return health_service.check()

    def second_failure_check():
        clock.advance(
            minutes=1,
        )

        start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=create_failure_metrics(),
            error_message="failure 2",
        )

        return health_service.check()

    result = run_monitoring_session(
        checker=SequenceChecker(
            [
                healthy_check,
                first_failure_check,
                second_failure_check,
            ]
        ),
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=3,
    )

    assert [
        event.status
        for event in result.events
    ] == [
        UpdateHealthStatus.HEALTHY,
        UpdateHealthStatus.WARNING,
        UpdateHealthStatus.ERROR,
    ]

    assert [
        transition.transition_type
        for transition in result.transitions
    ] == [
        UpdateHealthTransitionType.INITIAL,
        UpdateHealthTransitionType.DEGRADED,
        UpdateHealthTransitionType.DEGRADED,
    ]

    assert result.transitions[-1].current_status is (
        UpdateHealthStatus.ERROR
    )


def test_monitor_detects_error_to_healthy_recovery(
    tmp_path: Path,
) -> None:
    """異常状態の後に成功履歴が追加されると復旧を検出する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.FAILED,
        exit_code=3,
        metrics=create_failure_metrics(),
        error_message="initial failure",
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    def error_check():
        return health_service.check()

    def recovery_check():
        clock.advance(
            minutes=1,
        )

        success_run_id = start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.SUCCESS,
            exit_code=0,
            metrics=create_success_metrics(
                requested_code_count=1,
                updated_code_count=1,
            ),
        )

        report = health_service.check()

        assert report.latest_success is not None
        assert report.latest_success.run_id == (
            success_run_id
        )

        return report

    result = run_monitoring_session(
        checker=SequenceChecker(
            [
                error_check,
                recovery_check,
            ]
        ),
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    assert result.error_check_count == 1
    assert result.healthy_check_count == 1

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


def test_monitor_can_suppress_initial_state_with_real_database(
    tmp_path: Path,
) -> None:
    """実DB使用時も初回通知を抑制できる。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    result = run_monitoring_session(
        checker=health_service,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
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

    assert result.monitor_result.check_count == 2
    assert result.healthy_check_count == 2
    assert result.transition_count == 0


def test_monitor_records_checker_exception_and_recovers(
    tmp_path: Path,
) -> None:
    """チェック例外後に正常チェックへ復帰できる。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    checker = SequenceChecker(
        [
            lambda: (_ for _ in ()).throw(
                RuntimeError(
                    "temporary database error",
                )
            ),
            health_service.check,
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
            continue_on_check_error=True,
            maximum_consecutive_check_errors=3,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=2,
    )

    assert result.monitor_result.stop_reason is (
        MonitorStopReason.MAX_CHECKS_REACHED
    )
    assert result.monitor_result.check_count == 2
    assert result.monitor_result.successful_check_count == 1
    assert result.monitor_result.failed_check_count == 1
    assert result.monitor_result.consecutive_error_count == 0

    assert len(
        result.errors,
    ) == 1
    assert "temporary database error" in str(
        result.errors[0].error,
    )

    assert len(
        result.events,
    ) == 1
    assert result.events[0].status is (
        UpdateHealthStatus.HEALTHY
    )

    assert determine_exit_code(
        result,
    ) == EXIT_SUCCESS


def test_monitor_stops_after_consecutive_checker_errors(
    tmp_path: Path,
) -> None:
    """連続チェック例外が上限に達したら異常終了する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    checker = SequenceChecker(
        [
            lambda: (_ for _ in ()).throw(
                RuntimeError(
                    "failure 1",
                )
            ),
            lambda: (_ for _ in ()).throw(
                RuntimeError(
                    "failure 2",
                )
            ),
        ]
    )

    result = run_monitoring_session(
        checker=checker,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
            continue_on_check_error=True,
            maximum_consecutive_check_errors=2,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=10,
    )

    assert result.monitor_result.stop_reason is (
        MonitorStopReason.CHECK_FAILED
    )
    assert result.monitor_result.completed_normally is False
    assert result.monitor_result.check_count == 2
    assert result.monitor_result.failed_check_count == 2
    assert result.monitor_result.consecutive_error_count == 2

    assert len(
        result.errors,
    ) == 2
    assert result.events == ()
    assert result.transitions == ()

    assert determine_exit_code(
        result,
    ) == EXIT_MONITOR_FAILED


def test_monitor_stops_on_external_stop_request(
    tmp_path: Path,
) -> None:
    """外部停止要求を受けて安全に監視を終了する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    stop_values = iter(
        [
            False,
            False,
            True,
        ]
    )

    result = run_monitoring_session(
        checker=health_service,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        stop_requested=lambda: next(
            stop_values,
        ),
    )

    assert result.monitor_result.stop_reason is (
        MonitorStopReason.STOP_REQUESTED
    )
    assert result.monitor_result.completed_normally is True
    assert result.monitor_result.check_count == 1
    assert result.monitor_result.successful_check_count == 1
    assert result.monitor_result.failed_check_count == 0

    assert determine_exit_code(
        result,
    ) == EXIT_SUCCESS


def test_monitor_summary_and_transition_use_real_database_values(
    tmp_path: Path,
) -> None:
    """実DBの監視結果を表示用文字列へ変換する。"""

    clock = MutableClock(
        BASE_TIME,
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    run_id = start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    health_service = create_health_service(
        repository,
        clock,
    )

    result = run_monitoring_session(
        checker=health_service,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=1,
    )

    transition_text = format_transition(
        result.transitions[0],
    )
    summary_text = format_monitor_summary(
        result,
    )

    assert "initial" in transition_text
    assert "healthy" in transition_text
    assert run_id in (
        result.transitions[0]
        .current_report
        .latest_run.run_id
    )

    assert (
        "Update Health Monitor Summary"
        in summary_text
    )
    assert "Checks                  : 1" in summary_text
    assert "Successful checks       : 1" in summary_text
    assert "Healthy results         : 1" in summary_text
    assert "State transitions       : 1" in summary_text


def test_monitor_survives_repository_reopen(
    tmp_path: Path,
) -> None:
    """DB再オープン後も保存済み履歴を監視できる。"""

    clock = MutableClock(
        BASE_TIME,
    )
    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path,
    )

    first_repository = UpdateRunRepository(
        database_path,
        now_provider=clock.now,
        run_id_provider=lambda: "run-001",
    )

    start_and_finish_run(
        first_repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(),
    )

    reopened_repository = UpdateRunRepository(
        database_path,
        now_provider=clock.now,
    )

    health_service = create_health_service(
        reopened_repository,
        clock,
    )

    result = run_monitoring_session(
        checker=health_service,
        monitor_policy=UpdateHealthMonitorPolicy(
            check_interval_seconds=0,
        ),
        sleeper=lambda _seconds: None,
        now_provider=clock.now,
        max_checks=1,
    )

    assert result.healthy_check_count == 1
    assert result.transition_count == 1

    latest_run = (
        result.transitions[0]
        .current_report
        .latest_run
    )

    assert latest_run is not None
    assert latest_run.run_id == "run-001"
    assert reopened_repository.count() == 1