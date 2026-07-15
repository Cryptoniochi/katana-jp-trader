"""J-Quants自動更新基盤の健全性を確認するCLI。"""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database import initialize_database
from app.logger import create_logger
from app.monitoring.update_health_service import (
    DEFAULT_ERROR_FAILURE_COUNT,
    DEFAULT_ERROR_STALE_SECONDS,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_RUNNING_TIMEOUT_SECONDS,
    DEFAULT_WARNING_FAILURE_COUNT,
    DEFAULT_WARNING_STALE_SECONDS,
    UpdateHealthPolicy,
    UpdateHealthReport,
    UpdateHealthService,
    UpdateHealthStatus,
)
from app.monitoring.update_run_repository import (
    UpdateRunRepository,
    UpdateRunRepositoryError,
)
from app.settings import settings


EXIT_HEALTHY = 0
EXIT_WARNING = 1
EXIT_ERROR = 2
EXIT_EXECUTION_ERROR = 3


def parse_arguments(
    arguments: list[str] | None = None,
) -> argparse.Namespace:
    """監視CLIの引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "J-Quants自動更新の実行履歴を確認し、"
            "現在の健全性を判定します。"
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=settings.database_path,
        help=(
            "実行履歴を保存したSQLiteデータベース。"
            f"既定値: {settings.database_path}"
        ),
    )

    parser.add_argument(
        "--history-limit",
        type=int,
        default=DEFAULT_HISTORY_LIMIT,
        help=(
            "ヘルスチェックに使用する履歴件数。"
            f"既定値: {DEFAULT_HISTORY_LIMIT}"
        ),
    )

    parser.add_argument(
        "--warning-failures",
        type=int,
        default=DEFAULT_WARNING_FAILURE_COUNT,
        help=(
            "WARNINGとする連続失敗回数。"
            f"既定値: {DEFAULT_WARNING_FAILURE_COUNT}"
        ),
    )

    parser.add_argument(
        "--error-failures",
        type=int,
        default=DEFAULT_ERROR_FAILURE_COUNT,
        help=(
            "ERRORとする連続失敗回数。"
            f"既定値: {DEFAULT_ERROR_FAILURE_COUNT}"
        ),
    )

    parser.add_argument(
        "--warning-stale-seconds",
        type=float,
        default=DEFAULT_WARNING_STALE_SECONDS,
        help=(
            "最終成功からこの秒数以上経過した場合に"
            "WARNINGとします。"
            f"既定値: {DEFAULT_WARNING_STALE_SECONDS}"
        ),
    )

    parser.add_argument(
        "--error-stale-seconds",
        type=float,
        default=DEFAULT_ERROR_STALE_SECONDS,
        help=(
            "最終成功からこの秒数以上経過した場合に"
            "ERRORとします。"
            f"既定値: {DEFAULT_ERROR_STALE_SECONDS}"
        ),
    )

    parser.add_argument(
        "--running-timeout-seconds",
        type=float,
        default=DEFAULT_RUNNING_TIMEOUT_SECONDS,
        help=(
            "実行中状態を異常とみなす秒数。"
            f"既定値: {DEFAULT_RUNNING_TIMEOUT_SECONDS}"
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="判定結果をJSON形式で標準出力します。",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "標準出力を抑制し、終了コードだけで"
            "判定できるようにします。"
        ),
    )

    return parser.parse_args(
        arguments
    )


def create_health_policy(
    *,
    history_limit: int,
    warning_failure_count: int,
    error_failure_count: int,
    warning_stale_seconds: float,
    error_stale_seconds: float,
    running_timeout_seconds: float,
) -> UpdateHealthPolicy:
    """CLI指定値からヘルスチェック条件を作成する。"""

    return UpdateHealthPolicy(
        history_limit=history_limit,
        warning_failure_count=warning_failure_count,
        error_failure_count=error_failure_count,
        warning_stale_seconds=warning_stale_seconds,
        error_stale_seconds=error_stale_seconds,
        running_timeout_seconds=running_timeout_seconds,
    )


def determine_exit_code(
    report: UpdateHealthReport,
) -> int:
    """ヘルスチェック結果から終了コードを決定する。"""

    if report.status is UpdateHealthStatus.HEALTHY:
        return EXIT_HEALTHY

    if report.status is UpdateHealthStatus.WARNING:
        return EXIT_WARNING

    return EXIT_ERROR


def format_datetime(
    value: datetime | None,
) -> str:
    """日時を表示用文字列へ変換する。"""

    if value is None:
        return "-"

    return value.isoformat()


def format_optional_seconds(
    value: float | None,
) -> str:
    """経過秒数を表示用文字列へ変換する。"""

    if value is None:
        return "-"

    return f"{value:.1f}"


def format_health_report(
    report: UpdateHealthReport,
) -> str:
    """ヘルスチェック結果を人間向け文字列へ変換する。"""

    latest_run_status = (
        report.latest_run.status.value
        if report.latest_run is not None
        else "-"
    )

    latest_run_id = (
        report.latest_run.run_id
        if report.latest_run is not None
        else "-"
    )

    latest_run_started_at = (
        report.latest_run.started_at
        if report.latest_run is not None
        else None
    )

    latest_success_run_id = (
        report.latest_success.run_id
        if report.latest_success is not None
        else "-"
    )

    latest_success_finished_at = (
        (
            report.latest_success.finished_at
            or report.latest_success.started_at
        )
        if report.latest_success is not None
        else None
    )

    return "\n".join(
        [
            "=" * 60,
            "Project KATANA - Update Health Check",
            "=" * 60,
            f"status                         : {report.status.value}",
            f"checked_at                     : {format_datetime(report.checked_at)}",
            f"reason                         : {report.reason}",
            f"latest_run_id                  : {latest_run_id}",
            f"latest_run_status              : {latest_run_status}",
            (
                "latest_run_started_at          : "
                f"{format_datetime(latest_run_started_at)}"
            ),
            f"latest_success_run_id          : {latest_success_run_id}",
            (
                "latest_success_at              : "
                f"{format_datetime(latest_success_finished_at)}"
            ),
            (
                "consecutive_failure_count      : "
                f"{report.consecutive_failure_count}"
            ),
            (
                "seconds_since_latest_run       : "
                f"{format_optional_seconds(report.seconds_since_latest_run)}"
            ),
            (
                "seconds_since_latest_success   : "
                f"{format_optional_seconds(report.seconds_since_latest_success)}"
            ),
            "=" * 60,
        ]
    )


def health_report_to_dict(
    report: UpdateHealthReport,
) -> dict[str, Any]:
    """ヘルスチェック結果をJSON互換形式へ変換する。"""

    latest_run = report.latest_run
    latest_success = report.latest_success

    return {
        "status": report.status.value,
        "checked_at": report.checked_at.isoformat(),
        "reason": report.reason,
        "is_healthy": report.is_healthy,
        "requires_attention": report.requires_attention,
        "consecutive_failure_count": (
            report.consecutive_failure_count
        ),
        "seconds_since_latest_run": (
            report.seconds_since_latest_run
        ),
        "seconds_since_latest_success": (
            report.seconds_since_latest_success
        ),
        "latest_run": (
            {
                "run_id": latest_run.run_id,
                "process_name": latest_run.process_name,
                "status": latest_run.status.value,
                "started_at": latest_run.started_at.isoformat(),
                "finished_at": (
                    latest_run.finished_at.isoformat()
                    if latest_run.finished_at is not None
                    else None
                ),
                "exit_code": latest_run.exit_code,
                "error_message": latest_run.error_message,
                "metrics": asdict(
                    latest_run.metrics
                ),
            }
            if latest_run is not None
            else None
        ),
        "latest_success": (
            {
                "run_id": latest_success.run_id,
                "started_at": (
                    latest_success.started_at.isoformat()
                ),
                "finished_at": (
                    latest_success.finished_at.isoformat()
                    if latest_success.finished_at is not None
                    else None
                ),
            }
            if latest_success is not None
            else None
        ),
    }


def format_health_report_json(
    report: UpdateHealthReport,
) -> str:
    """ヘルスチェック結果をJSON文字列へ変換する。"""

    return json.dumps(
        health_report_to_dict(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def log_health_report(
    logger: logging.Logger,
    report: UpdateHealthReport,
) -> None:
    """ヘルスチェック結果を状態別にログへ出力する。"""

    message = (
        "自動更新ヘルスチェック: "
        "status=%s reason=%s "
        "consecutive_failures=%d "
        "seconds_since_latest_run=%s "
        "seconds_since_latest_success=%s"
    )

    arguments = (
        report.status.value,
        report.reason,
        report.consecutive_failure_count,
        report.seconds_since_latest_run,
        report.seconds_since_latest_success,
    )

    if report.status is UpdateHealthStatus.HEALTHY:
        logger.info(
            message,
            *arguments,
        )
        return

    if report.status is UpdateHealthStatus.WARNING:
        logger.warning(
            message,
            *arguments,
        )
        return

    logger.error(
        message,
        *arguments,
    )


def run_health_check(
    *,
    repository: UpdateRunRepository,
    policy: UpdateHealthPolicy,
) -> UpdateHealthReport:
    """指定Repositoryを使ってヘルスチェックを実行する。"""

    return UpdateHealthService(
        repository=repository,
        policy=policy,
    ).check()


def main(
    arguments: list[str] | None = None,
) -> int:
    """自動更新ヘルスチェックCLIを実行する。"""

    parsed_arguments = parse_arguments(
        arguments
    )

    settings.create_directories()

    logger = create_logger(
        settings.logs_dir
    )

    try:
        initialize_database(
            parsed_arguments.database
        )

        policy = create_health_policy(
            history_limit=(
                parsed_arguments.history_limit
            ),
            warning_failure_count=(
                parsed_arguments.warning_failures
            ),
            error_failure_count=(
                parsed_arguments.error_failures
            ),
            warning_stale_seconds=(
                parsed_arguments.warning_stale_seconds
            ),
            error_stale_seconds=(
                parsed_arguments.error_stale_seconds
            ),
            running_timeout_seconds=(
                parsed_arguments.running_timeout_seconds
            ),
        )

        repository = UpdateRunRepository(
            parsed_arguments.database
        )

        report = run_health_check(
            repository=repository,
            policy=policy,
        )

        log_health_report(
            logger=logger,
            report=report,
        )

        if not parsed_arguments.quiet:
            if parsed_arguments.json:
                print(
                    format_health_report_json(
                        report
                    )
                )
            else:
                print(
                    format_health_report(
                        report
                    )
                )

        return determine_exit_code(
            report
        )

    except (
        OSError,
        UpdateRunRepositoryError,
        ValueError,
    ) as error:
        logger.error(
            "自動更新ヘルスチェックを"
            "実行できませんでした: %s",
            error,
        )

        if not parsed_arguments.quiet:
            if parsed_arguments.json:
                print(
                    json.dumps(
                        {
                            "status": "execution_error",
                            "reason": str(error),
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(
                    "自動更新ヘルスチェックを"
                    f"実行できませんでした: {error}"
                )

        return EXIT_EXECUTION_ERROR


if __name__ == "__main__":
    raise SystemExit(
        main()
    )