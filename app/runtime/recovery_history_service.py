"""Recovery履歴の登録とDashboard集計を行うService。"""

from datetime import datetime, timezone

from app.dashboard.recovery_summary import (
    RecoveryStatus as DashboardRecoveryStatus,
)
from app.dashboard.recovery_summary import RecoverySummary
from app.runtime.recovery_history_models import (
    RecoveryComponent,
    RecoveryHistoryEntry,
)
from app.runtime.recovery_history_repository import (
    RecoveryHistoryRepository,
)
from app.runtime.recovery_models import (
    RecoveryResult,
    RecoveryStatus as RuntimeRecoveryStatus,
)


class RecoveryHistoryService:
    """Recovery結果を履歴化し、Dashboard向けに集計する。"""

    def __init__(
        self,
        repository: RecoveryHistoryRepository,
    ) -> None:
        if not isinstance(
            repository,
            RecoveryHistoryRepository,
        ):
            raise TypeError(
                "repository must be a RecoveryHistoryRepository"
            )

        self._repository = repository

    def record(
        self,
        *,
        component: RecoveryComponent,
        result: RecoveryResult,
    ) -> RecoveryHistoryEntry:
        """RecoveryResultを履歴として保存する。"""

        if not isinstance(component, RecoveryComponent):
            raise TypeError(
                "component must be a RecoveryComponent"
            )

        if not isinstance(result, RecoveryResult):
            raise TypeError(
                "result must be a RecoveryResult"
            )

        entry = RecoveryHistoryEntry(
            component=component,
            result=result,
        )
        self._repository.add(entry)

        return entry

    def list_history(
        self,
        component: RecoveryComponent | None = None,
    ) -> tuple[RecoveryHistoryEntry, ...]:
        """Recovery履歴を返す。"""

        if component is None:
            return self._repository.list_all()

        return self._repository.list_by_component(component)

    def build_summary(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> RecoverySummary:
        """保存済み履歴からDashboard用サマリーを生成する。"""

        if generated_at is None:
            generated_at = datetime.now(timezone.utc)

        self._validate_datetime(
            name="generated_at",
            value=generated_at,
        )

        broker_entries = self._repository.list_by_component(
            RecoveryComponent.BROKER
        )
        runtime_entries = self._repository.list_by_component(
            RecoveryComponent.RUNTIME
        )

        latest_entry = self._repository.latest()

        return RecoverySummary(
            broker_attempts=sum(
                entry.attempt_count
                for entry in broker_entries
            ),
            broker_successes=sum(
                entry.success_count
                for entry in broker_entries
            ),
            broker_failures=sum(
                entry.failure_count
                for entry in broker_entries
            ),
            last_broker_recovery=self._latest_completed_at(
                broker_entries
            ),
            runtime_attempts=sum(
                entry.attempt_count
                for entry in runtime_entries
            ),
            runtime_successes=sum(
                entry.success_count
                for entry in runtime_entries
            ),
            runtime_failures=sum(
                entry.failure_count
                for entry in runtime_entries
            ),
            last_runtime_recovery=self._latest_completed_at(
                runtime_entries
            ),
            recovery_status=self._dashboard_status(
                latest_entry
            ),
            generated_at=generated_at,
        )

    @staticmethod
    def _latest_completed_at(
        entries: tuple[RecoveryHistoryEntry, ...],
    ) -> datetime | None:
        """指定履歴の最新完了日時を返す。"""

        if not entries:
            return None

        return entries[-1].completed_at

    @staticmethod
    def _dashboard_status(
        latest_entry: RecoveryHistoryEntry | None,
    ) -> DashboardRecoveryStatus:
        """最新Recovery結果をDashboard状態へ変換する。"""

        if latest_entry is None:
            return DashboardRecoveryStatus.NORMAL

        runtime_status = latest_entry.result.status

        if runtime_status is RuntimeRecoveryStatus.RETRYING:
            return DashboardRecoveryStatus.RECOVERING

        if runtime_status in {
            RuntimeRecoveryStatus.FAILED,
            RuntimeRecoveryStatus.ABORTED,
        }:
            return DashboardRecoveryStatus.FAILED

        return DashboardRecoveryStatus.NORMAL

    @staticmethod
    def _validate_datetime(
        *,
        name: str,
        value: datetime,
    ) -> None:
        """日時がtimezone-awareであることを検証する。"""

        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime")

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                f"{name} must be timezone-aware"
            )