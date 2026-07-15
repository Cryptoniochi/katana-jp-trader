"""自動更新ヘルスチェックのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.monitoring.update_health_service import (
    UpdateHealthPolicy,
    UpdateHealthService,
    UpdateHealthStatus,
)
from app.monitoring.update_run_repository import (
    UpdateRunMetrics,
    UpdateRunRecord,
    UpdateRunStatus,
)


NOW = datetime(
    2026,
    7,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeUpdateRunRepository:
    """テスト用の自動更新実行履歴Repository。"""

    def __init__(
        self,
        records: list[UpdateRunRecord],
    ) -> None:
        """返却する履歴を設定する。"""

        self.records = records
        self.calls: list[
            tuple[int, UpdateRunStatus | None]
        ] = []

    def list_recent(
        self,
        *,
        limit: int = 20,
        status: UpdateRunStatus | None = None,
    ) -> list[UpdateRunRecord]:
        """新しい順の履歴を返す。"""

        self.calls.append(
            (
                limit,
                status,
            )
        )

        records = self.records

        if status is not None:
            records = [
                record
                for record in records
                if record.status is status
            ]

        return records[:limit]


def create_record(
    run_id: str,
    status: UpdateRunStatus,
    *,
    started_at: datetime,
    finished_at: datetime | None = None,
    exit_code: int | None = None,
) -> UpdateRunRecord:
    """テスト用の実行履歴を作成する。"""

    return UpdateRunRecord(
        id=int(
            run_id.split("-")[-1]
        ),
        run_id=run_id,
        process_name="jquants-update",
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=exit_code,
        metrics=UpdateRunMetrics(
            requested_code_count=1,
            updated_code_count=(
                1
                if status
                is UpdateRunStatus.SUCCESS
                else 0
            ),
            failed_code_count=(
                1
                if status
                in {
                    UpdateRunStatus.PARTIAL_FAILURE,
                    UpdateRunStatus.FAILED,
                }
                else 0
            ),
            request_count=(
                1
                if status
                is not UpdateRunStatus.RUNNING
                else 0
            ),
            successful_request_count=(
                1
                if status
                is UpdateRunStatus.SUCCESS
                else 0
            ),
            failed_request_count=(
                1
                if status
                in {
                    UpdateRunStatus.PARTIAL_FAILURE,
                    UpdateRunStatus.FAILED,
                }
                else 0
            ),
        ),
        error_message=(
            "test failure"
            if status
            in {
                UpdateRunStatus.PARTIAL_FAILURE,
                UpdateRunStatus.FAILED,
            }
            else None
        ),
    )


def create_success(
    run_number: int,
    *,
    age_hours: float = 1,
) -> UpdateRunRecord:
    """正常終了履歴を作成する。"""

    finished_at = NOW - timedelta(
        hours=age_hours,
    )

    return create_record(
        f"run-{run_number}",
        UpdateRunStatus.SUCCESS,
        started_at=(
            finished_at
            - timedelta(minutes=5)
        ),
        finished_at=finished_at,
        exit_code=0,
    )


def create_failure(
    run_number: int,
    *,
    age_hours: float,
    status: UpdateRunStatus = (
        UpdateRunStatus.FAILED
    ),
) -> UpdateRunRecord:
    """失敗した終了履歴を作成する。"""

    finished_at = NOW - timedelta(
        hours=age_hours,
    )

    return create_record(
        f"run-{run_number}",
        status,
        started_at=(
            finished_at
            - timedelta(minutes=5)
        ),
        finished_at=finished_at,
        exit_code=(
            1
            if status
            is UpdateRunStatus.PARTIAL_FAILURE
            else 3
        ),
    )


def create_service(
    records: list[UpdateRunRecord],
    *,
    policy: UpdateHealthPolicy | None = None,
) -> tuple[
    FakeUpdateRunRepository,
    UpdateHealthService,
]:
    """固定日時でヘルスチェックサービスを作成する。"""

    repository = FakeUpdateRunRepository(
        records
    )

    service = UpdateHealthService(
        repository=repository,
        policy=policy,
        now_provider=lambda: NOW,
    )

    return repository, service


def test_health_returns_error_without_history() -> None:
    """履歴がなければ異常と判定する。"""

    _repository, service = create_service(
        []
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.latest_run is None
    assert report.latest_success is None
    assert report.consecutive_failure_count == 0
    assert report.seconds_since_latest_run is None
    assert report.seconds_since_latest_success is None
    assert report.requires_attention is True
    assert "履歴がありません" in report.reason


def test_health_returns_healthy_after_recent_success() -> None:
    """直近の正常終了が新しければ正常と判定する。"""

    success = create_success(
        1,
        age_hours=1,
    )

    repository, service = create_service(
        [success]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.HEALTHY
    )
    assert report.is_healthy is True
    assert report.latest_run == success
    assert report.latest_success == success
    assert report.consecutive_failure_count == 0
    assert report.seconds_since_latest_success == (
        pytest.approx(3600)
    )
    assert repository.calls == [
        (
            100,
            None,
        )
    ]


def test_health_warns_after_single_failure() -> None:
    """直近1回の失敗を警告と判定する。"""

    failure = create_failure(
        2,
        age_hours=1,
    )
    success = create_success(
        1,
        age_hours=2,
    )

    _repository, service = create_service(
        [
            failure,
            success,
        ]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.consecutive_failure_count == 1
    assert report.latest_success == success
    assert "直近" in report.reason


def test_health_warns_at_warning_failure_threshold() -> None:
    """連続失敗が警告閾値に達したら警告にする。"""

    records = [
        create_failure(
            3,
            age_hours=1,
        ),
        create_failure(
            2,
            age_hours=2,
        ),
        create_success(
            1,
            age_hours=3,
        ),
    ]

    _repository, service = create_service(
        records
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.consecutive_failure_count == 2
    assert "連続" in report.reason


def test_health_returns_error_at_error_failure_threshold() -> None:
    """連続失敗が異常閾値に達したら異常にする。"""

    records = [
        create_failure(
            run_number,
            age_hours=float(
                6 - run_number
            ),
        )
        for run_number in range(
            5,
            0,
            -1,
        )
    ]

    _repository, service = create_service(
        records
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.consecutive_failure_count == 5
    assert "異常閾値" in report.reason


def test_health_success_resets_consecutive_failures() -> None:
    """最新の成功で連続失敗数をリセットする。"""

    records = [
        create_success(
            3,
            age_hours=1,
        ),
        create_failure(
            2,
            age_hours=2,
        ),
        create_failure(
            1,
            age_hours=3,
        ),
    ]

    _repository, service = create_service(
        records
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.HEALTHY
    )
    assert report.consecutive_failure_count == 0


def test_health_warns_when_success_is_stale() -> None:
    """最終成功が警告時間以上前なら警告にする。"""

    success = create_success(
        1,
        age_hours=24,
    )

    _repository, service = create_service(
        [success]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.seconds_since_latest_success == (
        pytest.approx(
            24 * 60 * 60
        )
    )
    assert "一定時間" in report.reason


def test_health_errors_when_success_is_very_stale() -> None:
    """最終成功が異常時間以上前なら異常にする。"""

    success = create_success(
        1,
        age_hours=72,
    )

    _repository, service = create_service(
        [success]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.seconds_since_latest_success == (
        pytest.approx(
            72 * 60 * 60
        )
    )
    assert "長時間" in report.reason


def test_health_errors_without_successful_history() -> None:
    """失敗履歴しかなければ異常にする。"""

    failure = create_failure(
        1,
        age_hours=1,
    )

    policy = UpdateHealthPolicy(
        warning_failure_count=2,
        error_failure_count=5,
    )

    _repository, service = create_service(
        [failure],
        policy=policy,
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert report.latest_success is None
    assert "正常終了" in report.reason


def test_health_warns_while_run_is_active() -> None:
    """短時間の実行中状態を警告にする。"""

    running = create_record(
        "run-2",
        UpdateRunStatus.RUNNING,
        started_at=(
            NOW - timedelta(minutes=30)
        ),
    )
    success = create_success(
        1,
        age_hours=1,
    )

    _repository, service = create_service(
        [
            running,
            success,
        ]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.latest_run == running
    assert "実行中" in report.reason


def test_health_errors_when_run_exceeds_timeout() -> None:
    """実行中状態がタイムアウトを超えたら異常にする。"""

    running = create_record(
        "run-2",
        UpdateRunStatus.RUNNING,
        started_at=(
            NOW - timedelta(hours=2)
        ),
    )
    success = create_success(
        1,
        age_hours=3,
    )

    _repository, service = create_service(
        [
            running,
            success,
        ]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.ERROR
    )
    assert "長時間実行中" in report.reason


def test_health_warns_after_already_running_result() -> None:
    """多重起動による未実行を警告にする。"""

    already_running = create_record(
        "run-2",
        UpdateRunStatus.ALREADY_RUNNING,
        started_at=(
            NOW - timedelta(minutes=30)
        ),
        finished_at=(
            NOW - timedelta(minutes=30)
        ),
        exit_code=2,
    )
    success = create_success(
        1,
        age_hours=1,
    )

    _repository, service = create_service(
        [
            already_running,
            success,
        ]
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.consecutive_failure_count == 0
    assert "多重起動" in report.reason


def test_already_running_does_not_break_failure_streak() -> None:
    """多重起動記録を除外して連続失敗を数える。"""

    already_running = create_record(
        "run-3",
        UpdateRunStatus.ALREADY_RUNNING,
        started_at=(
            NOW - timedelta(minutes=30)
        ),
        finished_at=(
            NOW - timedelta(minutes=30)
        ),
        exit_code=2,
    )

    records = [
        create_failure(
            4,
            age_hours=0.25,
        ),
        already_running,
        create_failure(
            2,
            age_hours=1,
        ),
        create_success(
            1,
            age_hours=2,
        ),
    ]

    _repository, service = create_service(
        records
    )

    report = service.check()

    assert report.consecutive_failure_count == 2
    assert report.status is (
        UpdateHealthStatus.WARNING
    )


def test_health_uses_custom_failure_thresholds() -> None:
    """独自の連続失敗閾値を使用する。"""

    policy = UpdateHealthPolicy(
        warning_failure_count=1,
        error_failure_count=2,
    )

    records = [
        create_failure(
            2,
            age_hours=1,
        ),
        create_success(
            1,
            age_hours=2,
        ),
    ]

    _repository, service = create_service(
        records,
        policy=policy,
    )

    report = service.check()

    assert report.status is (
        UpdateHealthStatus.WARNING
    )
    assert report.consecutive_failure_count == 1


def test_health_rejects_naive_current_time() -> None:
    """タイムゾーンなしの現在日時を拒否する。"""

    repository = FakeUpdateRunRepository(
        [
            create_success(
                1,
                age_hours=1,
            )
        ]
    )

    service = UpdateHealthService(
        repository,
        now_provider=lambda: datetime(
            2026,
            7,
            16,
            12,
            0,
        ),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        service.check()


def test_health_rejects_future_run_time() -> None:
    """未来の実行履歴を拒否する。"""

    future_success = create_record(
        "run-1",
        UpdateRunStatus.SUCCESS,
        started_at=(
            NOW + timedelta(minutes=5)
        ),
        finished_at=(
            NOW + timedelta(minutes=10)
        ),
        exit_code=0,
    )

    _repository, service = create_service(
        [future_success]
    )

    with pytest.raises(
        ValueError,
        match="未来",
    ):
        service.check()


@pytest.mark.parametrize(
    (
        "policy_arguments",
        "message",
    ),
    [
        (
            {
                "history_limit": 0,
            },
            "履歴取得件数",
        ),
        (
            {
                "warning_failure_count": 0,
            },
            "警告連続失敗回数",
        ),
        (
            {
                "warning_failure_count": 3,
                "error_failure_count": 2,
            },
            "異常連続失敗回数",
        ),
        (
            {
                "warning_stale_seconds": 0,
            },
            "警告未成功秒数",
        ),
        (
            {
                "warning_stale_seconds": 100,
                "error_stale_seconds": 99,
            },
            "異常未成功秒数",
        ),
        (
            {
                "running_timeout_seconds": 0,
            },
            "実行中タイムアウト秒数",
        ),
    ],
)
def test_health_policy_rejects_invalid_values(
    policy_arguments: dict[str, int],
    message: str,
) -> None:
    """不正なヘルスチェック条件を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        UpdateHealthPolicy(
            **policy_arguments,
        )