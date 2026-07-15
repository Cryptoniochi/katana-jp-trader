"""自動更新ヘルスチェックを一定間隔で繰り返す監視ループ。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from time import sleep
from typing import Protocol

from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


DEFAULT_CHECK_INTERVAL_SECONDS = 60.0


class UpdateHealthChecker(Protocol):
    """自動更新ヘルスチェック処理のインターフェース。"""

    def check(self) -> UpdateHealthReport:
        """現在の健全性を返す。"""


class MonitorStopReason(StrEnum):
    """監視ループの終了理由。"""

    STOP_REQUESTED = "stop_requested"
    MAX_CHECKS_REACHED = "max_checks_reached"
    CHECK_FAILED = "check_failed"


@dataclass(frozen=True, slots=True)
class UpdateHealthMonitorPolicy:
    """監視ループの実行条件。"""

    check_interval_seconds: float = (
        DEFAULT_CHECK_INTERVAL_SECONDS
    )
    continue_on_check_error: bool = True
    maximum_consecutive_check_errors: int = 3

    def __post_init__(self) -> None:
        """不正な監視条件を拒否する。"""

        if self.check_interval_seconds < 0:
            raise ValueError(
                "監視間隔は0秒以上である必要があります。"
            )

        if self.maximum_consecutive_check_errors <= 0:
            raise ValueError(
                "最大連続チェックエラー回数は"
                "0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class UpdateHealthMonitorEvent:
    """監視ループで発生した1回のチェック結果。"""

    check_number: int
    checked_at: datetime
    report: UpdateHealthReport

    @property
    def status(self) -> UpdateHealthStatus:
        """ヘルスチェック状態を返す。"""

        return self.report.status


@dataclass(frozen=True, slots=True)
class UpdateHealthMonitorError:
    """監視ループで発生したチェック例外。"""

    check_number: int
    occurred_at: datetime
    consecutive_error_count: int
    error: Exception


@dataclass(frozen=True, slots=True)
class UpdateHealthMonitorResult:
    """監視ループ全体の終了結果。"""

    stop_reason: MonitorStopReason
    started_at: datetime
    finished_at: datetime

    check_count: int
    successful_check_count: int
    failed_check_count: int
    consecutive_error_count: int

    latest_event: UpdateHealthMonitorEvent | None
    latest_error: UpdateHealthMonitorError | None

    @property
    def duration_seconds(self) -> float:
        """監視ループの実行時間を秒数で返す。"""

        return (
            self.finished_at - self.started_at
        ).total_seconds()

    @property
    def completed_normally(self) -> bool:
        """監視要求または回数上限で正常終了したか返す。"""

        return self.stop_reason in {
            MonitorStopReason.STOP_REQUESTED,
            MonitorStopReason.MAX_CHECKS_REACHED,
        }


MonitorEventCallback = Callable[
    [UpdateHealthMonitorEvent],
    None,
]

MonitorErrorCallback = Callable[
    [UpdateHealthMonitorError],
    None,
]

StopRequestedCallback = Callable[
    [],
    bool,
]


class UpdateHealthMonitor:
    """自動更新ヘルスチェックを一定間隔で繰り返す。"""

    def __init__(
        self,
        checker: UpdateHealthChecker,
        *,
        policy: UpdateHealthMonitorPolicy | None = None,
        sleeper: Callable[[float], None] = sleep,
        now_provider: Callable[[], datetime] | None = None,
        event_callback: MonitorEventCallback | None = None,
        error_callback: MonitorErrorCallback | None = None,
    ) -> None:
        """監視に必要な依存処理と条件を設定する。"""

        self.checker = checker
        self.policy = (
            policy
            if policy is not None
            else UpdateHealthMonitorPolicy()
        )
        self.sleeper = sleeper
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.event_callback = event_callback
        self.error_callback = error_callback

    def run(
        self,
        *,
        stop_requested: StopRequestedCallback | None = None,
        max_checks: int | None = None,
    ) -> UpdateHealthMonitorResult:
        """停止要求または回数上限まで監視を繰り返す。

        ``max_checks`` はテストや単発確認で使用する。
        常駐運用では ``None`` を指定し、外部の停止要求で終了する。
        """

        if max_checks is not None and max_checks <= 0:
            raise ValueError(
                "最大チェック回数は0より大きい必要があります。"
            )

        resolved_stop_requested = (
            stop_requested
            if stop_requested is not None
            else lambda: False
        )

        started_at = self._current_time()

        check_count = 0
        successful_check_count = 0
        failed_check_count = 0
        consecutive_error_count = 0

        latest_event: UpdateHealthMonitorEvent | None = None
        latest_error: UpdateHealthMonitorError | None = None

        while True:
            if resolved_stop_requested():
                return self._create_result(
                    stop_reason=(
                        MonitorStopReason.STOP_REQUESTED
                    ),
                    started_at=started_at,
                    check_count=check_count,
                    successful_check_count=(
                        successful_check_count
                    ),
                    failed_check_count=failed_check_count,
                    consecutive_error_count=(
                        consecutive_error_count
                    ),
                    latest_event=latest_event,
                    latest_error=latest_error,
                )

            if (
                max_checks is not None
                and check_count >= max_checks
            ):
                return self._create_result(
                    stop_reason=(
                        MonitorStopReason.MAX_CHECKS_REACHED
                    ),
                    started_at=started_at,
                    check_count=check_count,
                    successful_check_count=(
                        successful_check_count
                    ),
                    failed_check_count=failed_check_count,
                    consecutive_error_count=(
                        consecutive_error_count
                    ),
                    latest_event=latest_event,
                    latest_error=latest_error,
                )

            check_count += 1

            try:
                report = self.checker.check()

            except Exception as error:
                failed_check_count += 1
                consecutive_error_count += 1

                latest_error = UpdateHealthMonitorError(
                    check_number=check_count,
                    occurred_at=self._current_time(),
                    consecutive_error_count=(
                        consecutive_error_count
                    ),
                    error=error,
                )

                if self.error_callback is not None:
                    self.error_callback(
                        latest_error
                    )

                should_stop = (
                    not self.policy.continue_on_check_error
                    or consecutive_error_count
                    >= (
                        self.policy
                        .maximum_consecutive_check_errors
                    )
                )

                if should_stop:
                    return self._create_result(
                        stop_reason=(
                            MonitorStopReason.CHECK_FAILED
                        ),
                        started_at=started_at,
                        check_count=check_count,
                        successful_check_count=(
                            successful_check_count
                        ),
                        failed_check_count=(
                            failed_check_count
                        ),
                        consecutive_error_count=(
                            consecutive_error_count
                        ),
                        latest_event=latest_event,
                        latest_error=latest_error,
                    )

            else:
                successful_check_count += 1
                consecutive_error_count = 0

                latest_event = UpdateHealthMonitorEvent(
                    check_number=check_count,
                    checked_at=self._current_time(),
                    report=report,
                )

                if self.event_callback is not None:
                    self.event_callback(
                        latest_event
                    )

            if (
                max_checks is not None
                and check_count >= max_checks
            ):
                continue

            if resolved_stop_requested():
                continue

            self.sleeper(
                self.policy.check_interval_seconds
            )

    def _create_result(
        self,
        *,
        stop_reason: MonitorStopReason,
        started_at: datetime,
        check_count: int,
        successful_check_count: int,
        failed_check_count: int,
        consecutive_error_count: int,
        latest_event: UpdateHealthMonitorEvent | None,
        latest_error: UpdateHealthMonitorError | None,
    ) -> UpdateHealthMonitorResult:
        """現在の監視状態から終了結果を作成する。"""

        finished_at = self._current_time()

        if finished_at < started_at:
            raise ValueError(
                "監視終了日時は開始日時以後である必要があります。"
            )

        return UpdateHealthMonitorResult(
            stop_reason=stop_reason,
            started_at=started_at,
            finished_at=finished_at,
            check_count=check_count,
            successful_check_count=(
                successful_check_count
            ),
            failed_check_count=failed_check_count,
            consecutive_error_count=(
                consecutive_error_count
            ),
            latest_event=latest_event,
            latest_error=latest_error,
        )

    def _current_time(self) -> datetime:
        """UTCの現在日時を返す。"""

        current_time = self.now_provider()

        if current_time.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current_time.astimezone(
            timezone.utc
        )