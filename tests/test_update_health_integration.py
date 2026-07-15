"""自動更新実行履歴・ヘルスチェック・監視表示の統合テスト。"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.check_update_health import (
    EXIT_ERROR,
    EXIT_HEALTHY,
    EXIT_WARNING,
    determine_exit_code,
    format_health_report,
    format_health_report_json,
)
from app.database import initialize_database
from app.monitoring.update_health_service import (
    UpdateHealthPolicy,
    UpdateHealthService,
    UpdateHealthStatus,
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
    12,
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
    """連番の実行IDを返す。"""

    def __init__(self) -> None:
        """連番を初期化する。"""

        self.next_number = 1

    def __call__(self) -> str:
        """次の実行IDを返す。"""

        run_id = (
            f"run-{self.next_number:03d}"
        )

        self.next_number += 1

        return run_id


def create_repository(
    tmp_path: Path,
    clock: MutableClock,
) -> UpdateRunRepository:
    """初期化済み実行履歴Repositoryを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path
    )

    return UpdateRunRepository(
        database_path,
        now_provider=clock.now,
        run_id_provider=(
            SequentialRunIdProvider()
        ),
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
        requested_code_count=(
            requested_code_count
        ),
        updated_code_count=(
            updated_code_count
        ),
        skipped_code_count=(
            skipped_code_count
        ),
        failed_code_count=0,
        business_date_count=4,
        request_count=4,
        successful_request_count=4,
        empty_request_count=0,
        failed_request_count=0,
        processed_bar_count=240,
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
    duration_minutes: float = 5,
) -> str:
    """実行履歴を開始し、指定状態で終了する。"""

    started = repository.start(
        process_name=(
            "jquants-incremental-update"
        ),
        requested_code_count=(
            metrics.requested_code_count
        ),
    )

    clock.advance(
        minutes=duration_minutes
    )

    repository.finish(
        started.run_id,
        status=status,
        exit_code=exit_code,
        metrics=metrics,
        error_message=error_message,
    )

    return started.run_id


def test_successful_run_is_persisted_and_health_is_healthy(
    tmp_path: Path,
) -> None:
    """正常終了履歴を保存し、正常判定できる。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.HEALTHY
    )
    assert report.is_healthy is True
    assert report.requires_attention is False

    assert report.latest_run is not None
    assert report.latest_run.run_id == run_id
    assert report.latest_run.status is (
        UpdateRunStatus.SUCCESS
    )

    assert report.latest_success is not None
    assert report.latest_success.run_id == (
        run_id
    )

    assert (
        report.consecutive_failure_count
        == 0
    )

    assert determine_exit_code(
        report
    ) == EXIT_HEALTHY


def test_partial_failure_is_persisted_and_health_is_warning(
    tmp_path: Path,
) -> None:
    """部分失敗を保存し、警告判定できる。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    partial_run_id = start_and_finish_run(
        repository,
        clock,
        status=(
            UpdateRunStatus.PARTIAL_FAILURE
        ),
        exit_code=1,
        metrics=create_partial_failure_metrics(),
        error_message="one request failed",
    )

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.requires_attention is True
    assert report.consecutive_failure_count == 1

    assert report.latest_run is not None
    assert report.latest_run.run_id == (
        partial_run_id
    )
    assert report.latest_run.status is (
        UpdateRunStatus.PARTIAL_FAILURE
    )
    assert report.latest_run.error_message == (
        "one request failed"
    )

    assert report.latest_success is not None

    assert determine_exit_code(
        report
    ) == EXIT_WARNING


def test_failed_run_without_success_is_error(
    tmp_path: Path,
) -> None:
    """正常終了履歴がなく失敗のみなら異常判定する。"""

    clock = MutableClock(
        BASE_TIME
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    run_id = start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.FAILED,
        exit_code=3,
        metrics=UpdateRunMetrics(
            requested_code_count=2,
            failed_code_count=2,
        ),
        error_message="calendar unavailable",
    )

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.latest_run is not None
    assert report.latest_run.run_id == run_id
    assert report.latest_success is None
    assert report.consecutive_failure_count == 1
    assert "正常終了" in report.reason

    assert determine_exit_code(
        report
    ) == EXIT_ERROR


def test_empty_repository_is_error(
    tmp_path: Path,
) -> None:
    """実行履歴がなければ異常判定する。"""

    clock = MutableClock(
        BASE_TIME
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.latest_run is None
    assert report.latest_success is None
    assert report.consecutive_failure_count == 0
    assert "履歴がありません" in report.reason

    assert determine_exit_code(
        report
    ) == EXIT_ERROR


def test_already_running_record_is_warning(
    tmp_path: Path,
) -> None:
    """多重起動で未実行となった履歴を警告判定する。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    already_running_id = (
        start_and_finish_run(
            repository,
            clock,
            status=(
                UpdateRunStatus.ALREADY_RUNNING
            ),
            exit_code=2,
            metrics=UpdateRunMetrics(
                requested_code_count=2,
                skipped_code_count=2,
            ),
            error_message=(
                "another process is running"
            ),
            duration_minutes=0,
        )
    )

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.consecutive_failure_count == 0

    assert report.latest_run is not None
    assert report.latest_run.run_id == (
        already_running_id
    )
    assert report.latest_run.status is (
        UpdateRunStatus.ALREADY_RUNNING
    )

    assert report.latest_success is not None
    assert report.latest_success.run_id == (
        success_run_id
    )

    assert "多重起動" in report.reason


def test_consecutive_failures_reach_error_threshold(
    tmp_path: Path,
) -> None:
    """連続失敗が異常閾値に達したら異常判定する。"""

    clock = MutableClock(
        BASE_TIME
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

    for failure_number in range(
        1,
        6,
    ):
        clock.advance(
            minutes=10
        )

        start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
                failed_code_count=1,
            ),
            error_message=(
                f"failure {failure_number}"
            ),
        )

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.consecutive_failure_count == 5
    assert "異常閾値" in report.reason


def test_success_resets_failure_streak(
    tmp_path: Path,
) -> None:
    """失敗後の成功で連続失敗数をリセットする。"""

    clock = MutableClock(
        BASE_TIME
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    for failure_number in range(
        1,
        3,
    ):
        start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
                failed_code_count=1,
            ),
            error_message=(
                f"failure {failure_number}"
            ),
        )

        clock.advance(
            minutes=10
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

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.HEALTHY
    )
    assert report.consecutive_failure_count == 0
    assert report.latest_success is not None
    assert report.latest_success.run_id == (
        success_run_id
    )


def test_failure_after_recovery_starts_new_failure_streak(
    tmp_path: Path,
) -> None:
    """復旧後の新たな失敗は連続失敗1回として数える。"""

    clock = MutableClock(
        BASE_TIME
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    for failure_number in range(
        1,
        3,
    ):
        start_and_finish_run(
            repository,
            clock,
            status=UpdateRunStatus.FAILED,
            exit_code=3,
            metrics=UpdateRunMetrics(
                requested_code_count=1,
                failed_code_count=1,
            ),
            error_message=(
                f"old failure {failure_number}"
            ),
        )

        clock.advance(
            minutes=10
        )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.SUCCESS,
        exit_code=0,
        metrics=create_success_metrics(
            requested_code_count=1,
            updated_code_count=1,
        ),
    )

    clock.advance(
        minutes=10
    )

    start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.FAILED,
        exit_code=3,
        metrics=UpdateRunMetrics(
            requested_code_count=1,
            failed_code_count=1,
        ),
        error_message="new failure",
    )

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.consecutive_failure_count == 1
    assert report.latest_run is not None
    assert report.latest_run.error_message == (
        "new failure"
    )


def test_stale_success_is_warning(
    tmp_path: Path,
) -> None:
    """最終成功から警告時間が経過したら警告判定する。"""

    clock = MutableClock(
        BASE_TIME
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
        duration_minutes=0,
    )

    clock.advance(
        hours=24
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert (
        report.seconds_since_latest_success
        == 24 * 60 * 60
    )
    assert "一定時間" in report.reason


def test_very_stale_success_is_error(
    tmp_path: Path,
) -> None:
    """最終成功から異常時間が経過したら異常判定する。"""

    clock = MutableClock(
        BASE_TIME
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
        duration_minutes=0,
    )

    clock.advance(
        hours=72
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert (
        report.seconds_since_latest_success
        == 72 * 60 * 60
    )
    assert "長時間" in report.reason


def test_running_record_is_warning_before_timeout(
    tmp_path: Path,
) -> None:
    """実行中履歴がタイムアウト前なら警告判定する。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    running_record = repository.start(
        process_name=(
            "jquants-incremental-update"
        ),
        requested_code_count=2,
    )

    clock.advance(
        minutes=30
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.latest_run is not None
    assert report.latest_run.run_id == (
        running_record.run_id
    )
    assert report.latest_run.status is (
        UpdateRunStatus.RUNNING
    )
    assert "実行中" in report.reason


def test_running_record_is_error_after_timeout(
    tmp_path: Path,
) -> None:
    """実行中履歴がタイムアウトに達したら異常判定する。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    repository.start(
        process_name=(
            "jquants-incremental-update"
        ),
        requested_code_count=2,
    )

    clock.advance(
        hours=2
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert "長時間実行中" in report.reason


def test_health_text_output_matches_repository_data(
    tmp_path: Path,
) -> None:
    """実DBから作成したレポートを人間向け表示へ変換する。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    output = format_health_report(
        report
    )

    assert (
        "Project KATANA - Update Health Check"
        in output
    )
    assert (
        "status                         : healthy"
        in output
    )
    assert run_id in output
    assert "latest_run_status" in output
    assert "success" in output
    assert "consecutive_failure_count" in output


def test_health_json_output_matches_repository_data(
    tmp_path: Path,
) -> None:
    """実DBから作成したレポートをJSON表示へ変換する。"""

    clock = MutableClock(
        BASE_TIME
    )
    repository = create_repository(
        tmp_path,
        clock,
    )

    run_id = start_and_finish_run(
        repository,
        clock,
        status=(
            UpdateRunStatus.PARTIAL_FAILURE
        ),
        exit_code=1,
        metrics=create_partial_failure_metrics(),
        error_message="one request failed",
    )

    clock.advance(
        minutes=10
    )

    policy = UpdateHealthPolicy(
        warning_failure_count=1,
        error_failure_count=5,
    )

    report = create_health_service(
        repository,
        clock,
        policy=policy,
    ).check()

    output = format_health_report_json(
        report
    )
    parsed = json.loads(
        output
    )

    assert parsed["status"] == "error"
    assert parsed["latest_run"]["run_id"] == (
        run_id
    )
    assert (
        parsed["latest_run"]["status"]
        == "partial_failure"
    )
    assert (
        parsed["latest_run"]["error_message"]
        == "one request failed"
    )
    assert (
        parsed["latest_run"]["metrics"][
            "failed_request_count"
        ]
        == 1
    )
    assert parsed["latest_success"] is None


def test_latest_success_and_latest_run_can_differ(
    tmp_path: Path,
) -> None:
    """直近失敗時も最新成功履歴を別に保持する。"""

    clock = MutableClock(
        BASE_TIME
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

    clock.advance(
        minutes=10
    )

    failure_run_id = start_and_finish_run(
        repository,
        clock,
        status=UpdateRunStatus.FAILED,
        exit_code=3,
        metrics=UpdateRunMetrics(
            requested_code_count=1,
            failed_code_count=1,
        ),
        error_message="temporary failure",
    )

    clock.advance(
        minutes=10
    )

    report = create_health_service(
        repository,
        clock,
    ).check()

    assert report.latest_run is not None
    assert report.latest_run.run_id == (
        failure_run_id
    )

    assert report.latest_success is not None
    assert report.latest_success.run_id == (
        success_run_id
    )

    assert report.latest_run.run_id != (
        report.latest_success.run_id
    )


def test_repository_and_health_service_survive_database_reopen(
    tmp_path: Path,
) -> None:
    """DBを再オープンしても実行履歴と健全性を復元できる。"""

    clock = MutableClock(
        BASE_TIME
    )
    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path
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

    clock.advance(
        minutes=10
    )

    reopened_repository = (
        UpdateRunRepository(
            database_path,
            now_provider=clock.now,
        )
    )

    report = UpdateHealthService(
        repository=reopened_repository,
        now_provider=clock.now,
    ).check()

    assert report.status is (
        UpdateHealthStatus.HEALTHY
    )
    assert report.latest_run is not None
    assert report.latest_run.run_id == (
        "run-001"
    )
    assert reopened_repository.count() == 1