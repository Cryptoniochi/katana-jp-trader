"""自動更新実行履歴からシステムの健全性を判定する。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from app.monitoring.update_run_repository import (
    UpdateRunRecord,
    UpdateRunStatus,
)


DEFAULT_HISTORY_LIMIT = 100
DEFAULT_WARNING_FAILURE_COUNT = 2
DEFAULT_ERROR_FAILURE_COUNT = 5
DEFAULT_WARNING_STALE_SECONDS = 24 * 60 * 60
DEFAULT_ERROR_STALE_SECONDS = 72 * 60 * 60
DEFAULT_RUNNING_TIMEOUT_SECONDS = 2 * 60 * 60


class UpdateRunHistoryReader(Protocol):
    """自動更新実行履歴を読み込むインターフェース。"""

    def list_recent(
        self,
        *,
        limit: int = 20,
        status: UpdateRunStatus | None = None,
    ) -> list[UpdateRunRecord]:
        """新しい順に実行履歴を返す。"""


class UpdateHealthStatus(StrEnum):
    """自動更新基盤の健全性。"""

    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class UpdateHealthPolicy:
    """ヘルスチェックの判定条件。"""

    history_limit: int = DEFAULT_HISTORY_LIMIT
    warning_failure_count: int = DEFAULT_WARNING_FAILURE_COUNT
    error_failure_count: int = DEFAULT_ERROR_FAILURE_COUNT
    warning_stale_seconds: float = DEFAULT_WARNING_STALE_SECONDS
    error_stale_seconds: float = DEFAULT_ERROR_STALE_SECONDS
    running_timeout_seconds: float = DEFAULT_RUNNING_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        """不正な判定条件を拒否する。"""

        if self.history_limit <= 0:
            raise ValueError(
                "履歴取得件数は0より大きい必要があります。"
            )

        if self.warning_failure_count <= 0:
            raise ValueError(
                "警告連続失敗回数は0より大きい必要があります。"
            )

        if self.error_failure_count < self.warning_failure_count:
            raise ValueError(
                "異常連続失敗回数は"
                "警告連続失敗回数以上である必要があります。"
            )

        if self.warning_stale_seconds <= 0:
            raise ValueError(
                "警告未成功秒数は0より大きい必要があります。"
            )

        if self.error_stale_seconds < self.warning_stale_seconds:
            raise ValueError(
                "異常未成功秒数は"
                "警告未成功秒数以上である必要があります。"
            )

        if self.running_timeout_seconds <= 0:
            raise ValueError(
                "実行中タイムアウト秒数は"
                "0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class UpdateHealthReport:
    """自動更新基盤のヘルスチェック結果。"""

    status: UpdateHealthStatus
    checked_at: datetime
    reason: str

    latest_run: UpdateRunRecord | None
    latest_success: UpdateRunRecord | None

    consecutive_failure_count: int
    seconds_since_latest_run: float | None
    seconds_since_latest_success: float | None

    @property
    def is_healthy(self) -> bool:
        """正常状態か返す。"""

        return self.status is UpdateHealthStatus.HEALTHY

    @property
    def requires_attention(self) -> bool:
        """確認が必要な状態か返す。"""

        return self.status is not UpdateHealthStatus.HEALTHY


class UpdateHealthService:
    """自動更新実行履歴から健全性を判定する。"""

    FAILURE_STATUSES = frozenset(
        {
            UpdateRunStatus.PARTIAL_FAILURE,
            UpdateRunStatus.FAILED,
        }
    )

    def __init__(
        self,
        repository: UpdateRunHistoryReader,
        *,
        policy: UpdateHealthPolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """実行履歴Repositoryと判定条件を設定する。"""

        self.repository = repository
        self.policy = policy or UpdateHealthPolicy()
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def check(self) -> UpdateHealthReport:
        """現在の自動更新基盤の健全性を返す。"""

        checked_at = self._current_time()

        records = self.repository.list_recent(
            limit=self.policy.history_limit,
        )

        if not records:
            return UpdateHealthReport(
                status=UpdateHealthStatus.ERROR,
                checked_at=checked_at,
                reason=(
                    "自動更新の実行履歴がありません。"
                ),
                latest_run=None,
                latest_success=None,
                consecutive_failure_count=0,
                seconds_since_latest_run=None,
                seconds_since_latest_success=None,
            )

        latest_run = records[0]
        latest_success = self._find_latest_success(
            records
        )
        consecutive_failure_count = (
            self._count_consecutive_failures(
                records
            )
        )

        seconds_since_latest_run = (
            self._elapsed_seconds(
                checked_at,
                latest_run.started_at,
            )
        )

        seconds_since_latest_success = (
            self._elapsed_seconds(
                checked_at,
                latest_success.finished_at
                or latest_success.started_at,
            )
            if latest_success is not None
            else None
        )

        status, reason = self._evaluate(
            checked_at=checked_at,
            latest_run=latest_run,
            latest_success=latest_success,
            consecutive_failure_count=(
                consecutive_failure_count
            ),
            seconds_since_latest_success=(
                seconds_since_latest_success
            ),
        )

        return UpdateHealthReport(
            status=status,
            checked_at=checked_at,
            reason=reason,
            latest_run=latest_run,
            latest_success=latest_success,
            consecutive_failure_count=(
                consecutive_failure_count
            ),
            seconds_since_latest_run=(
                seconds_since_latest_run
            ),
            seconds_since_latest_success=(
                seconds_since_latest_success
            ),
        )

    def _evaluate(
        self,
        *,
        checked_at: datetime,
        latest_run: UpdateRunRecord,
        latest_success: UpdateRunRecord | None,
        consecutive_failure_count: int,
        seconds_since_latest_success: float | None,
    ) -> tuple[UpdateHealthStatus, str]:
        """実行履歴から健全性と理由を決定する。"""

        if latest_run.status is UpdateRunStatus.RUNNING:
            running_seconds = self._elapsed_seconds(
                checked_at,
                latest_run.started_at,
            )

            if (
                running_seconds
                >= self.policy.running_timeout_seconds
            ):
                return (
                    UpdateHealthStatus.ERROR,
                    (
                        "自動更新が長時間実行中のままです。 "
                        f"run_id={latest_run.run_id} "
                        f"running_seconds={running_seconds:.1f}"
                    ),
                )

            return (
                UpdateHealthStatus.WARNING,
                (
                    "自動更新が現在実行中です。 "
                    f"run_id={latest_run.run_id} "
                    f"running_seconds={running_seconds:.1f}"
                ),
            )

        if (
            consecutive_failure_count
            >= self.policy.error_failure_count
        ):
            return (
                UpdateHealthStatus.ERROR,
                (
                    "自動更新の連続失敗回数が"
                    "異常閾値に達しました。 "
                    f"consecutive_failures="
                    f"{consecutive_failure_count}"
                ),
            )

        if latest_success is None:
            return (
                UpdateHealthStatus.ERROR,
                (
                    "正常終了した自動更新履歴がありません。 "
                    f"latest_status={latest_run.status.value}"
                ),
            )

        if (
            seconds_since_latest_success is not None
            and seconds_since_latest_success
            >= self.policy.error_stale_seconds
        ):
            return (
                UpdateHealthStatus.ERROR,
                (
                    "最後の正常更新から長時間経過しています。 "
                    f"seconds_since_success="
                    f"{seconds_since_latest_success:.1f}"
                ),
            )

        if (
            consecutive_failure_count
            >= self.policy.warning_failure_count
        ):
            return (
                UpdateHealthStatus.WARNING,
                (
                    "自動更新が連続して失敗しています。 "
                    f"consecutive_failures="
                    f"{consecutive_failure_count}"
                ),
            )

        if (
            seconds_since_latest_success is not None
            and seconds_since_latest_success
            >= self.policy.warning_stale_seconds
        ):
            return (
                UpdateHealthStatus.WARNING,
                (
                    "最後の正常更新から一定時間が"
                    "経過しています。 "
                    f"seconds_since_success="
                    f"{seconds_since_latest_success:.1f}"
                ),
            )

        if latest_run.status in self.FAILURE_STATUSES:
            return (
                UpdateHealthStatus.WARNING,
                (
                    "直近の自動更新が失敗しています。 "
                    f"latest_status={latest_run.status.value} "
                    f"run_id={latest_run.run_id}"
                ),
            )

        if (
            latest_run.status
            is UpdateRunStatus.ALREADY_RUNNING
        ):
            return (
                UpdateHealthStatus.WARNING,
                (
                    "直近の自動更新は多重起動により"
                    "開始されませんでした。 "
                    f"run_id={latest_run.run_id}"
                ),
            )

        return (
            UpdateHealthStatus.HEALTHY,
            (
                "直近の自動更新は正常終了しています。 "
                f"run_id={latest_run.run_id}"
            ),
        )

    @classmethod
    def _count_consecutive_failures(
        cls,
        records: list[UpdateRunRecord],
    ) -> int:
        """最新履歴から連続する失敗件数を返す。"""

        failure_count = 0

        for record in records:
            if record.status in cls.FAILURE_STATUSES:
                failure_count += 1
                continue

            if (
                record.status
                is UpdateRunStatus.ALREADY_RUNNING
            ):
                continue

            break

        return failure_count

    @staticmethod
    def _find_latest_success(
        records: list[UpdateRunRecord],
    ) -> UpdateRunRecord | None:
        """最新の正常終了履歴を返す。"""

        for record in records:
            if record.status.is_successful:
                return record

        return None

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

    @staticmethod
    def _elapsed_seconds(
        later: datetime,
        earlier: datetime,
    ) -> float:
        """2つの日時の経過秒数を返す。"""

        if earlier.tzinfo is None:
            raise ValueError(
                "実行履歴の日時には"
                "タイムゾーンが必要です。"
            )

        elapsed_seconds = (
            later
            - earlier.astimezone(timezone.utc)
        ).total_seconds()

        if elapsed_seconds < 0:
            raise ValueError(
                "実行履歴の日時が"
                "ヘルスチェック日時より未来です。"
            )

        return elapsed_seconds