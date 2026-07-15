"""自動更新ヘルスチェックCLIのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.check_update_health import (
    EXIT_ERROR,
    EXIT_HEALTHY,
    EXIT_WARNING,
    create_health_policy,
    determine_exit_code,
    format_health_report,
    format_health_report_json,
    format_optional_seconds,
    health_report_to_dict,
    parse_arguments,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)
from app.monitoring.update_run_repository import (
    UpdateRunMetrics,
    UpdateRunRecord,
    UpdateRunStatus,
)


CHECKED_AT = datetime(
    2026,
    7,
    16,
    12,
    0,
    tzinfo=timezone.utc,
)

STARTED_AT = datetime(
    2026,
    7,
    16,
    10,
    55,
    tzinfo=timezone.utc,
)

FINISHED_AT = datetime(
    2026,
    7,
    16,
    11,
    0,
    tzinfo=timezone.utc,
)


def create_run_record(
    *,
    status: UpdateRunStatus = UpdateRunStatus.SUCCESS,
    run_id: str = "run-001",
) -> UpdateRunRecord:
    """CLIテスト用の実行履歴を作成する。"""

    return UpdateRunRecord(
        id=1,
        run_id=run_id,
        process_name="jquants-update",
        status=status,
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        exit_code=(
            0
            if status is UpdateRunStatus.SUCCESS
            else 3
        ),
        metrics=UpdateRunMetrics(
            requested_code_count=2,
            updated_code_count=(
                2
                if status is UpdateRunStatus.SUCCESS
                else 0
            ),
            failed_code_count=(
                1
                if status is UpdateRunStatus.FAILED
                else 0
            ),
            request_count=2,
            successful_request_count=(
                2
                if status is UpdateRunStatus.SUCCESS
                else 1
            ),
            failed_request_count=(
                1
                if status is UpdateRunStatus.FAILED
                else 0
            ),
            processed_bar_count=120,
        ),
        error_message=(
            "test failure"
            if status is UpdateRunStatus.FAILED
            else None
        ),
    )


def create_report(
    status: UpdateHealthStatus,
) -> UpdateHealthReport:
    """指定状態のヘルスチェック結果を作成する。"""

    latest_run_status = (
        UpdateRunStatus.SUCCESS
        if status is UpdateHealthStatus.HEALTHY
        else UpdateRunStatus.FAILED
    )

    latest_run = create_run_record(
        status=latest_run_status
    )

    latest_success = (
        latest_run
        if status is UpdateHealthStatus.HEALTHY
        else create_run_record(
            status=UpdateRunStatus.SUCCESS,
            run_id="run-000",
        )
    )

    return UpdateHealthReport(
        status=status,
        checked_at=CHECKED_AT,
        reason=f"{status.value} reason",
        latest_run=latest_run,
        latest_success=latest_success,
        consecutive_failure_count=(
            0
            if status is UpdateHealthStatus.HEALTHY
            else 2
        ),
        seconds_since_latest_run=3600.0,
        seconds_since_latest_success=3600.0,
    )


def test_parse_arguments_reads_monitoring_options(
    tmp_path: Path,
) -> None:
    """監視CLIの引数を読み込む。"""

    database_path = tmp_path / "katana.db"

    arguments = parse_arguments(
        [
            "--database",
            str(database_path),
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
            "--json",
            "--quiet",
        ]
    )

    assert arguments.database == database_path
    assert arguments.history_limit == 50
    assert arguments.warning_failures == 3
    assert arguments.error_failures == 6
    assert arguments.warning_stale_seconds == 1000
    assert arguments.error_stale_seconds == 2000
    assert arguments.running_timeout_seconds == 300
    assert arguments.json is True
    assert arguments.quiet is True


def test_create_health_policy() -> None:
    """CLI値からヘルスチェック条件を作成する。"""

    policy = create_health_policy(
        history_limit=50,
        warning_failure_count=3,
        error_failure_count=6,
        warning_stale_seconds=1000,
        error_stale_seconds=2000,
        running_timeout_seconds=300,
    )

    assert policy.history_limit == 50
    assert policy.warning_failure_count == 3
    assert policy.error_failure_count == 6
    assert policy.warning_stale_seconds == 1000
    assert policy.error_stale_seconds == 2000
    assert policy.running_timeout_seconds == 300


@pytest.mark.parametrize(
    (
        "health_status",
        "expected_exit_code",
    ),
    [
        (
            UpdateHealthStatus.HEALTHY,
            EXIT_HEALTHY,
        ),
        (
            UpdateHealthStatus.WARNING,
            EXIT_WARNING,
        ),
        (
            UpdateHealthStatus.ERROR,
            EXIT_ERROR,
        ),
    ],
)
def test_determine_exit_code(
    health_status: UpdateHealthStatus,
    expected_exit_code: int,
) -> None:
    """健全性に対応する終了コードを返す。"""

    report = create_report(
        health_status
    )

    assert determine_exit_code(
        report
    ) == expected_exit_code


def test_format_health_report_contains_summary() -> None:
    """人間向け表示に主要情報を含める。"""

    report = create_report(
        UpdateHealthStatus.WARNING
    )

    message = format_health_report(
        report
    )

    assert "Project KATANA" in message
    assert "status" in message
    assert "warning" in message
    assert "warning reason" in message
    assert "run-001" in message
    assert "consecutive_failure_count" in message
    assert "3600.0" in message


def test_format_health_report_handles_missing_history() -> None:
    """履歴がない結果を安全に表示する。"""

    report = UpdateHealthReport(
        status=UpdateHealthStatus.ERROR,
        checked_at=CHECKED_AT,
        reason="履歴がありません。",
        latest_run=None,
        latest_success=None,
        consecutive_failure_count=0,
        seconds_since_latest_run=None,
        seconds_since_latest_success=None,
    )

    message = format_health_report(
        report
    )

    assert "error" in message
    assert "履歴がありません" in message
    assert "latest_run_id                  : -" in message
    assert "latest_success_run_id          : -" in message


def test_health_report_to_dict() -> None:
    """ヘルスチェック結果を辞書へ変換する。"""

    report = create_report(
        UpdateHealthStatus.HEALTHY
    )

    result = health_report_to_dict(
        report
    )

    assert result["status"] == "healthy"
    assert result["is_healthy"] is True
    assert result["requires_attention"] is False
    assert result["consecutive_failure_count"] == 0

    latest_run = result["latest_run"]

    assert isinstance(
        latest_run,
        dict,
    )
    assert latest_run["run_id"] == "run-001"
    assert latest_run["status"] == "success"
    assert latest_run["metrics"][
        "requested_code_count"
    ] == 2


def test_health_report_to_dict_handles_missing_runs() -> None:
    """履歴なし結果を辞書へ変換する。"""

    report = UpdateHealthReport(
        status=UpdateHealthStatus.ERROR,
        checked_at=CHECKED_AT,
        reason="no history",
        latest_run=None,
        latest_success=None,
        consecutive_failure_count=0,
        seconds_since_latest_run=None,
        seconds_since_latest_success=None,
    )

    result = health_report_to_dict(
        report
    )

    assert result["latest_run"] is None
    assert result["latest_success"] is None


def test_format_health_report_json() -> None:
    """JSON形式の表示を作成する。"""

    report = create_report(
        UpdateHealthStatus.WARNING
    )

    text = format_health_report_json(
        report
    )

    parsed = json.loads(
        text
    )

    assert parsed["status"] == "warning"
    assert parsed["reason"] == "warning reason"
    assert parsed["latest_run"]["run_id"] == "run-001"
    assert parsed["latest_success"]["run_id"] == "run-000"


def test_format_optional_seconds() -> None:
    """経過秒数を表示用文字列へ変換する。"""

    assert format_optional_seconds(
        123.456
    ) == "123.5"

    assert format_optional_seconds(
        None
    ) == "-"