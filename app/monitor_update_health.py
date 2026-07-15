"""J-Quants自動更新ヘルスチェックを常駐実行するCLI。"""

import argparse
import logging
import signal
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from time import sleep
from types import FrameType

from app.database import initialize_database
from app.logger import create_logger
from app.monitoring.update_health_monitor import (
    DEFAULT_CHECK_INTERVAL_SECONDS,
    MonitorStopReason,
    UpdateHealthChecker,
    UpdateHealthMonitor,
    UpdateHealthMonitorError,
    UpdateHealthMonitorEvent,
    UpdateHealthMonitorPolicy,
    UpdateHealthMonitorResult,
)
from app.monitoring.update_health_service import (
    DEFAULT_ERROR_FAILURE_COUNT,
    DEFAULT_ERROR_STALE_SECONDS,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_RUNNING_TIMEOUT_SECONDS,
    DEFAULT_WARNING_FAILURE_COUNT,
    DEFAULT_WARNING_STALE_SECONDS,
    UpdateHealthPolicy,
    UpdateHealthService,
    UpdateHealthStatus,
)
from app.monitoring.update_health_transition import (
    UpdateHealthTransition,
    UpdateHealthTransitionDetector,
    UpdateHealthTransitionType,
)
from app.monitoring.update_run_repository import (
    UpdateRunRepository,
    UpdateRunRepositoryError,
)
from app.settings import settings


EXIT_SUCCESS = 0
EXIT_MONITOR_FAILED = 1
EXIT_EXECUTION_ERROR = 2

DEFAULT_MAXIMUM_CONSECUTIVE_CHECK_ERRORS = 3
DEFAULT_LOG_LEVEL = "INFO"

SUPPORTED_LOG_LEVELS = (
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
)


@dataclass(frozen=True, slots=True)
class MonitoringSessionResult:
    """1回の常駐監視セッション結果。"""

    monitor_result: UpdateHealthMonitorResult
    events: tuple[UpdateHealthMonitorEvent, ...]
    errors: tuple[UpdateHealthMonitorError, ...]
    transitions: tuple[UpdateHealthTransition, ...]

    @property
    def transition_count(self) -> int:
        """通知対象となった状態変化件数を返す。"""

        return len(
            self.transitions
        )

    @property
    def healthy_check_count(self) -> int:
        """HEALTHYだったチェック件数を返す。"""

        return sum(
            event.status is UpdateHealthStatus.HEALTHY
            for event in self.events
        )

    @property
    def warning_check_count(self) -> int:
        """WARNINGだったチェック件数を返す。"""

        return sum(
            event.status is UpdateHealthStatus.WARNING
            for event in self.events
        )

    @property
    def error_check_count(self) -> int:
        """ERRORだったチェック件数を返す。"""

        return sum(
            event.status is UpdateHealthStatus.ERROR
            for event in self.events
        )


class SignalStopController:
    """OSシグナルを安全な停止要求へ変換する。"""

    def __init__(self) -> None:
        """停止イベントとシグナル設定を初期化する。"""

        self._stop_event = Event()
        self._previous_handlers: dict[
            signal.Signals,
            signal.Handlers,
        ] = {}

    @property
    def is_stop_requested(self) -> bool:
        """停止要求を受信済みか返す。"""

        return self._stop_event.is_set()

    def request_stop(self) -> None:
        """監視停止を要求する。"""

        self._stop_event.set()

    def stop_requested(self) -> bool:
        """監視ループ用の停止判定を返す。"""

        return self.is_stop_requested

    def install(self) -> None:
        """SIGINT・SIGTERMのハンドラを設定する。"""

        signals = [
            signal.SIGINT,
        ]

        if hasattr(
            signal,
            "SIGTERM",
        ):
            signals.append(
                signal.SIGTERM
            )

        for signal_number in signals:
            if signal_number in self._previous_handlers:
                continue

            self._previous_handlers[
                signal_number
            ] = signal.getsignal(
                signal_number
            )

            signal.signal(
                signal_number,
                self._handle_signal,
            )

    def restore(self) -> None:
        """変更前のシグナルハンドラへ戻す。"""

        for (
            signal_number,
            previous_handler,
        ) in self._previous_handlers.items():
            signal.signal(
                signal_number,
                previous_handler,
            )

        self._previous_handlers.clear()

    def _handle_signal(
        self,
        signal_number: int,
        frame: FrameType | None,
    ) -> None:
        """OSシグナル受信時に停止要求を設定する。"""

        del signal_number
        del frame

        self.request_stop()

    def __enter__(
        self,
    ) -> "SignalStopController":
        """with文開始時にシグナルハンドラを設定する。"""

        self.install()

        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> bool:
        """with文終了時にシグナルハンドラを復元する。"""

        del exception_type
        del exception
        del traceback

        self.restore()

        return False


def parse_arguments(
    arguments: list[str] | None = None,
) -> argparse.Namespace:
    """常駐監視CLIの引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "J-Quants自動更新の実行履歴を一定間隔で確認し、"
            "健全性が変化したときだけ通知します。"
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
        "--interval-seconds",
        type=float,
        default=DEFAULT_CHECK_INTERVAL_SECONDS,
        help=(
            "ヘルスチェックの実行間隔秒数。"
            f"既定値: {DEFAULT_CHECK_INTERVAL_SECONDS}"
        ),
    )

    parser.add_argument(
        "--max-checks",
        type=int,
        default=None,
        help=(
            "監視を終了する最大チェック回数。"
            "省略時は停止要求を受けるまで継続します。"
        ),
    )

    parser.add_argument(
        "--maximum-check-errors",
        type=int,
        default=(
            DEFAULT_MAXIMUM_CONSECUTIVE_CHECK_ERRORS
        ),
        help=(
            "監視を停止する連続チェックエラー回数。"
            "既定値: "
            f"{DEFAULT_MAXIMUM_CONSECUTIVE_CHECK_ERRORS}"
        ),
    )

    parser.add_argument(
        "--stop-on-check-error",
        action="store_true",
        help=(
            "ヘルスチェック処理で例外が発生した時点で"
            "監視を終了します。"
        ),
    )

    parser.add_argument(
        "--suppress-initial",
        action="store_true",
        help="監視開始時の初回状態通知を抑制します。",
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
            "最終成功からWARNINGとするまでの秒数。"
            f"既定値: {DEFAULT_WARNING_STALE_SECONDS}"
        ),
    )

    parser.add_argument(
        "--error-stale-seconds",
        type=float,
        default=DEFAULT_ERROR_STALE_SECONDS,
        help=(
            "最終成功からERRORとするまでの秒数。"
            f"既定値: {DEFAULT_ERROR_STALE_SECONDS}"
        ),
    )

    parser.add_argument(
        "--running-timeout-seconds",
        type=float,
        default=DEFAULT_RUNNING_TIMEOUT_SECONDS,
        help=(
            "実行中状態をERRORとするまでの秒数。"
            f"既定値: {DEFAULT_RUNNING_TIMEOUT_SECONDS}"
        ),
    )

    parser.add_argument(
        "--log-level",
        choices=SUPPORTED_LOG_LEVELS,
        default=DEFAULT_LOG_LEVEL,
        help=(
            "監視ログの出力レベル。"
            f"既定値: {DEFAULT_LOG_LEVEL}"
        ),
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="状態変化と終了サマリーの標準出力を抑制します。",
    )

    return parser.parse_args(
        arguments
    )


def create_health_policy(
    arguments: argparse.Namespace,
) -> UpdateHealthPolicy:
    """CLI引数からヘルスチェック条件を作成する。"""

    return UpdateHealthPolicy(
        history_limit=(
            arguments.history_limit
        ),
        warning_failure_count=(
            arguments.warning_failures
        ),
        error_failure_count=(
            arguments.error_failures
        ),
        warning_stale_seconds=(
            arguments.warning_stale_seconds
        ),
        error_stale_seconds=(
            arguments.error_stale_seconds
        ),
        running_timeout_seconds=(
            arguments.running_timeout_seconds
        ),
    )


def create_monitor_policy(
    arguments: argparse.Namespace,
) -> UpdateHealthMonitorPolicy:
    """CLI引数から監視ループ条件を作成する。"""

    return UpdateHealthMonitorPolicy(
        check_interval_seconds=(
            arguments.interval_seconds
        ),
        continue_on_check_error=(
            not arguments.stop_on_check_error
        ),
        maximum_consecutive_check_errors=(
            arguments.maximum_check_errors
        ),
    )


def configure_logger_level(
    logger: logging.Logger,
    level_name: str,
) -> None:
    """Loggerと既存Handlerへログレベルを設定する。"""

    normalized_level = level_name.strip().upper()

    if normalized_level not in SUPPORTED_LOG_LEVELS:
        raise ValueError(
            "未対応のログレベルです。 "
            f"level={level_name}"
        )

    level = getattr(
        logging,
        normalized_level,
    )

    logger.setLevel(
        level
    )

    for handler in logger.handlers:
        handler.setLevel(
            level
        )


def format_transition(
    transition: UpdateHealthTransition,
) -> str:
    """状態変化を標準出力用文字列へ変換する。"""

    previous_status = (
        transition.previous_status.value
        if transition.previous_status is not None
        else "-"
    )

    return "\n".join(
        [
            "-" * 60,
            (
                "Update health transition: "
                f"{transition.transition_type.value}"
            ),
            (
                "Previous status : "
                f"{previous_status}"
            ),
            (
                "Current status  : "
                f"{transition.current_status.value}"
            ),
            (
                "Check number    : "
                f"{transition.check_number}"
            ),
            (
                "Detected at     : "
                f"{transition.detected_at.isoformat()}"
            ),
            (
                "Reason          : "
                f"{transition.current_report.reason}"
            ),
            "-" * 60,
        ]
    )


def format_monitor_summary(
    result: MonitoringSessionResult,
) -> str:
    """監視終了結果を人間向け文字列へ変換する。"""

    monitor_result = result.monitor_result

    return "\n".join(
        [
            "=" * 60,
            "Project KATANA - Update Health Monitor Summary",
            "=" * 60,
            (
                "Stop reason             : "
                f"{monitor_result.stop_reason.value}"
            ),
            (
                "Started at              : "
                f"{monitor_result.started_at.isoformat()}"
            ),
            (
                "Finished at             : "
                f"{monitor_result.finished_at.isoformat()}"
            ),
            (
                "Duration seconds        : "
                f"{monitor_result.duration_seconds:.1f}"
            ),
            (
                "Checks                  : "
                f"{monitor_result.check_count}"
            ),
            (
                "Successful checks       : "
                f"{monitor_result.successful_check_count}"
            ),
            (
                "Failed checks           : "
                f"{monitor_result.failed_check_count}"
            ),
            (
                "Healthy results         : "
                f"{result.healthy_check_count}"
            ),
            (
                "Warning results         : "
                f"{result.warning_check_count}"
            ),
            (
                "Error results           : "
                f"{result.error_check_count}"
            ),
            (
                "State transitions       : "
                f"{result.transition_count}"
            ),
            "=" * 60,
        ]
    )


def log_transition(
    logger: logging.Logger,
    transition: UpdateHealthTransition,
) -> None:
    """状態変化を重大度に応じてログ出力する。"""

    if (
        transition.transition_type
        is UpdateHealthTransitionType.DEGRADED
    ):
        if (
            transition.current_status
            is UpdateHealthStatus.ERROR
        ):
            logger.error(
                "%s",
                transition.message,
            )
        else:
            logger.warning(
                "%s",
                transition.message,
            )

        return

    if (
        transition.transition_type
        is UpdateHealthTransitionType.RECOVERED
    ):
        logger.info(
            "%s",
            transition.message,
        )
        return

    if (
        transition.current_status
        is UpdateHealthStatus.ERROR
    ):
        logger.error(
            "%s",
            transition.message,
        )
    elif (
        transition.current_status
        is UpdateHealthStatus.WARNING
    ):
        logger.warning(
            "%s",
            transition.message,
        )
    else:
        logger.info(
            "%s",
            transition.message,
        )


def log_monitor_error(
    logger: logging.Logger,
    monitor_error: UpdateHealthMonitorError,
) -> None:
    """監視チェック例外をログへ出力する。"""

    logger.error(
        "自動更新ヘルスチェック処理に失敗しました。 "
        "check_number=%d consecutive_errors=%d error=%s",
        monitor_error.check_number,
        monitor_error.consecutive_error_count,
        monitor_error.error,
    )


def run_monitoring_session(
    *,
    checker: UpdateHealthChecker,
    monitor_policy: UpdateHealthMonitorPolicy,
    transition_detector: (
        UpdateHealthTransitionDetector | None
    ) = None,
    sleeper: Callable[[float], None] = sleep,
    now_provider: Callable[[], datetime] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    max_checks: int | None = None,
    transition_callback: (
        Callable[[UpdateHealthTransition], None] | None
    ) = None,
    error_callback: (
        Callable[[UpdateHealthMonitorError], None] | None
    ) = None,
) -> MonitoringSessionResult:
    """監視ループと状態変化検知を統合して実行する。"""

    detector = (
        transition_detector
        if transition_detector is not None
        else UpdateHealthTransitionDetector()
    )

    events: list[
        UpdateHealthMonitorEvent
    ] = []
    errors: list[
        UpdateHealthMonitorError
    ] = []
    transitions: list[
        UpdateHealthTransition
    ] = []

    def handle_event(
        event: UpdateHealthMonitorEvent,
    ) -> None:
        events.append(
            event
        )

        transition = detector.detect(
            event
        )

        if transition is None:
            return

        transitions.append(
            transition
        )

        if transition_callback is not None:
            transition_callback(
                transition
            )

    def handle_error(
        monitor_error: UpdateHealthMonitorError,
    ) -> None:
        errors.append(
            monitor_error
        )

        if error_callback is not None:
            error_callback(
                monitor_error
            )

    monitor = UpdateHealthMonitor(
        checker=checker,
        policy=monitor_policy,
        sleeper=sleeper,
        now_provider=now_provider,
        event_callback=handle_event,
        error_callback=handle_error,
    )

    monitor_result = monitor.run(
        stop_requested=stop_requested,
        max_checks=max_checks,
    )

    return MonitoringSessionResult(
        monitor_result=monitor_result,
        events=tuple(
            events
        ),
        errors=tuple(
            errors
        ),
        transitions=tuple(
            transitions
        ),
    )


def determine_exit_code(
    result: MonitoringSessionResult,
) -> int:
    """監視終了結果からプロセス終了コードを決定する。"""

    if (
        result.monitor_result.stop_reason
        is MonitorStopReason.CHECK_FAILED
    ):
        return EXIT_MONITOR_FAILED

    return EXIT_SUCCESS


def main(
    arguments: list[str] | None = None,
) -> int:
    """自動更新ヘルスチェック常駐監視を実行する。"""

    parsed_arguments = parse_arguments(
        arguments
    )

    settings.create_directories()

    logger = create_logger(
        settings.logs_dir
    )

    try:
        configure_logger_level(
            logger,
            parsed_arguments.log_level,
        )

        initialize_database(
            parsed_arguments.database
        )

        repository = UpdateRunRepository(
            parsed_arguments.database
        )

        health_service = UpdateHealthService(
            repository=repository,
            policy=create_health_policy(
                parsed_arguments
            ),
        )

        monitor_policy = create_monitor_policy(
            parsed_arguments
        )

        transition_detector = (
            UpdateHealthTransitionDetector(
                notify_initial_state=(
                    not parsed_arguments
                    .suppress_initial
                )
            )
        )

        logger.info(
            "自動更新ヘルス監視を開始します。 "
            "database=%s interval_seconds=%.1f "
            "max_checks=%s",
            parsed_arguments.database,
            monitor_policy.check_interval_seconds,
            parsed_arguments.max_checks,
        )

        def show_transition(
            transition: UpdateHealthTransition,
        ) -> None:
            log_transition(
                logger,
                transition,
            )

            if not parsed_arguments.quiet:
                print(
                    format_transition(
                        transition
                    )
                )

        with SignalStopController() as stop_controller:
            result = run_monitoring_session(
                checker=health_service,
                monitor_policy=monitor_policy,
                transition_detector=(
                    transition_detector
                ),
                stop_requested=(
                    stop_controller
                    .stop_requested
                ),
                max_checks=(
                    parsed_arguments.max_checks
                ),
                transition_callback=(
                    show_transition
                ),
                error_callback=lambda error: (
                    log_monitor_error(
                        logger,
                        error,
                    )
                ),
            )

        logger.info(
            "自動更新ヘルス監視を終了しました。 "
            "stop_reason=%s checks=%d "
            "successful_checks=%d failed_checks=%d "
            "transitions=%d duration_seconds=%.1f",
            result.monitor_result.stop_reason.value,
            result.monitor_result.check_count,
            result.monitor_result.successful_check_count,
            result.monitor_result.failed_check_count,
            result.transition_count,
            result.monitor_result.duration_seconds,
        )

        if not parsed_arguments.quiet:
            print(
                format_monitor_summary(
                    result
                )
            )

        return determine_exit_code(
            result
        )

    except KeyboardInterrupt:
        logger.info(
            "キーボード割り込みにより"
            "自動更新ヘルス監視を終了しました。"
        )

        if not parsed_arguments.quiet:
            print(
                "キーボード割り込みにより"
                "監視を終了しました。"
            )

        return EXIT_SUCCESS

    except (
        OSError,
        UpdateRunRepositoryError,
        ValueError,
    ) as error:
        logger.error(
            "自動更新ヘルス監視を"
            "実行できませんでした: %s",
            error,
        )

        if not parsed_arguments.quiet:
            print(
                "自動更新ヘルス監視を"
                f"実行できませんでした: {error}"
            )

        return EXIT_EXECUTION_ERROR


if __name__ == "__main__":
    raise SystemExit(
        main()
    )