"""RecoveryEventからDashboard用RecoverySummaryを生成する。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.dashboard.recovery_summary import (
    RecoveryStatus as DashboardRecoveryStatus,
)
from app.dashboard.recovery_summary import RecoverySummary
from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_event_repository import (
    RecoveryEventRepository,
)


class RecoveryEventSummaryService:
    """RecoveryEventをBroker・Runtime別に集計する。"""

    SUMMARY_SOURCES = {
        RecoverySource.BROKER,
        RecoverySource.RUNTIME,
    }

    def __init__(
        self,
        repository: RecoveryEventRepository,
    ) -> None:
        if not isinstance(
            repository,
            RecoveryEventRepository,
        ):
            raise TypeError(
                "repository must be a RecoveryEventRepository"
            )

        self._repository = repository

    def build_summary(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> RecoverySummary:
        """保存済みRecoveryEventからDashboard用サマリーを生成する。"""

        if generated_at is None:
            generated_at = datetime.now(timezone.utc)

        self._validate_datetime(
            name="generated_at",
            value=generated_at,
        )

        broker_events = self._repository.list_by_source(
            RecoverySource.BROKER
        )
        runtime_events = self._repository.list_by_source(
            RecoverySource.RUNTIME
        )

        latest_event = self._latest_relevant_event(
            broker_events=broker_events,
            runtime_events=runtime_events,
        )

        broker_counts = self._aggregate_events(
            broker_events
        )
        runtime_counts = self._aggregate_events(
            runtime_events
        )

        return RecoverySummary(
            broker_attempts=broker_counts[0],
            broker_successes=broker_counts[1],
            broker_failures=broker_counts[2],
            last_broker_recovery=self._latest_completed_at(
                broker_events
            ),
            runtime_attempts=runtime_counts[0],
            runtime_successes=runtime_counts[1],
            runtime_failures=runtime_counts[2],
            last_runtime_recovery=self._latest_completed_at(
                runtime_events
            ),
            recovery_status=self._dashboard_status(
                latest_event
            ),
            generated_at=generated_at,
        )

    @classmethod
    def _aggregate_events(
        cls,
        events: tuple[RecoveryEvent, ...],
    ) -> tuple[int, int, int]:
        """Event列から試行・成功・失敗件数を集計する。"""

        attempts = 0
        successes = 0
        failures = 0

        for event in events:
            event_attempts = cls._metadata_count(
                event=event,
                key="attempt_count",
                fallback=cls._fallback_attempt_count(
                    event
                ),
            )
            event_successes = cls._metadata_count(
                event=event,
                key="success_count",
                fallback=cls._fallback_success_count(
                    event
                ),
            )
            event_failures = cls._metadata_count(
                event=event,
                key="failure_count",
                fallback=cls._fallback_failure_count(
                    event
                ),
            )

            if (
                event_successes + event_failures
                != event_attempts
            ):
                raise ValueError(
                    "RecoveryEvent attempt_count must "
                    "equal success_count + failure_count"
                )

            attempts += event_attempts
            successes += event_successes
            failures += event_failures

        return attempts, successes, failures

    @staticmethod
    def _metadata_count(
        *,
        event: RecoveryEvent,
        key: str,
        fallback: int,
    ) -> int:
        """Metadata内の件数を検証して返す。"""

        value = event.metadata.get(
            key,
            fallback,
        )

        if isinstance(value, bool) or not isinstance(
            value,
            int,
        ):
            raise TypeError(
                f"RecoveryEvent metadata {key} "
                "must be an int"
            )

        if value < 0:
            raise ValueError(
                f"RecoveryEvent metadata {key} "
                "must be greater than or equal to 0"
            )

        return value

    @staticmethod
    def _fallback_attempt_count(
        event: RecoveryEvent,
    ) -> int:
        """MetadataがないEventの試行件数を補完する。"""

        if event.status in {
            RecoveryEventStatus.STARTED,
            RecoveryEventStatus.RETRYING,
            RecoveryEventStatus.SKIPPED,
        }:
            return 0

        return 1

    @staticmethod
    def _fallback_success_count(
        event: RecoveryEvent,
    ) -> int:
        """MetadataがないEventの成功件数を補完する。"""

        return int(
            event.status
            is RecoveryEventStatus.SUCCEEDED
        )

    @staticmethod
    def _fallback_failure_count(
        event: RecoveryEvent,
    ) -> int:
        """MetadataがないEventの失敗件数を補完する。"""

        return int(
            event.status
            in {
                RecoveryEventStatus.FAILED,
                RecoveryEventStatus.ABORTED,
            }
        )

    @staticmethod
    def _latest_completed_at(
        events: tuple[RecoveryEvent, ...],
    ) -> datetime | None:
        """指定Event列の最新完了日時を返す。"""

        completed_values = tuple(
            event.completed_at
            for event in events
            if event.completed_at is not None
        )

        if not completed_values:
            return None

        return max(completed_values)

    @staticmethod
    def _latest_relevant_event(
        *,
        broker_events: tuple[RecoveryEvent, ...],
        runtime_events: tuple[RecoveryEvent, ...],
    ) -> RecoveryEvent | None:
        """Broker・Runtimeのうち最新Eventを返す。"""

        events = broker_events + runtime_events

        if not events:
            return None

        return max(
            events,
            key=lambda event: (
                event.started_at,
                (
                    event.completed_at
                    if event.completed_at is not None
                    else event.started_at
                ),
                event.event_id,
            ),
        )

    @staticmethod
    def _dashboard_status(
        latest_event: RecoveryEvent | None,
    ) -> DashboardRecoveryStatus:
        """最新Event状態をDashboard状態へ変換する。"""

        if latest_event is None:
            return DashboardRecoveryStatus.NORMAL

        if latest_event.status in {
            RecoveryEventStatus.STARTED,
            RecoveryEventStatus.RETRYING,
        }:
            return DashboardRecoveryStatus.RECOVERING

        if latest_event.status in {
            RecoveryEventStatus.FAILED,
            RecoveryEventStatus.ABORTED,
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
            raise TypeError(
                f"{name} must be a datetime"
            )

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{name} must be timezone-aware"
            )