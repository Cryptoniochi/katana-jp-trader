"""RecoveryEventの登録と検索をまとめるService。"""

from __future__ import annotations

from app.runtime.recovery_event_mapper import (
    map_runtime_recovery_result,
)
from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_event_repository import (
    RecoveryEventRepository,
)
from app.runtime.recovery_models import RecoveryResult


class RecoveryEventService:
    """RecoveryEventの生成・登録・検索を統括する。"""

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

    def record(
        self,
        event: RecoveryEvent,
    ) -> RecoveryEvent:
        """既に生成済みのRecoveryEventを保存する。"""

        if not isinstance(event, RecoveryEvent):
            raise TypeError(
                "event must be a RecoveryEvent"
            )

        return self._repository.add(event)

    def record_runtime_result(
        self,
        result: RecoveryResult,
        *,
        category: RecoveryEventCategory = (
            RecoveryEventCategory.RECOVERY
        ),
    ) -> RecoveryEvent:
        """Runtime RecoveryResultをEventへ変換して保存する。"""

        if not isinstance(result, RecoveryResult):
            raise TypeError(
                "result must be a RecoveryResult"
            )

        if not isinstance(
            category,
            RecoveryEventCategory,
        ):
            raise TypeError(
                "category must be a RecoveryEventCategory"
            )

        event = map_runtime_recovery_result(
            result,
            category=category,
        )

        return self._repository.add(event)

    def list_events(
        self,
        *,
        source: RecoverySource | None = None,
        category: RecoveryEventCategory | None = None,
        status: RecoveryEventStatus | None = None,
    ) -> tuple[RecoveryEvent, ...]:
        """条件に一致するRecoveryEventを返す。"""

        self._validate_filters(
            source=source,
            category=category,
            status=status,
        )

        events = self._repository.list_all()

        return tuple(
            event
            for event in events
            if (
                source is None
                or event.source is source
            )
            and (
                category is None
                or event.category is category
            )
            and (
                status is None
                or event.status is status
            )
        )

    def latest(
        self,
        *,
        source: RecoverySource | None = None,
    ) -> RecoveryEvent | None:
        """最新のRecoveryEventを返す。"""

        if source is not None and not isinstance(
            source,
            RecoverySource,
        ):
            raise TypeError(
                "source must be a RecoverySource or None"
            )

        return self._repository.latest(
            source=source
        )

    def count(
        self,
        *,
        source: RecoverySource | None = None,
        category: RecoveryEventCategory | None = None,
        status: RecoveryEventStatus | None = None,
    ) -> int:
        """条件に一致するRecoveryEvent件数を返す。"""

        self._validate_filters(
            source=source,
            category=category,
            status=status,
        )

        return self._repository.count(
            source=source,
            category=category,
            status=status,
        )

    def clear(self) -> None:
        """すべてのRecoveryEventを削除する。"""

        self._repository.clear()

    @staticmethod
    def _validate_filters(
        *,
        source: RecoverySource | None,
        category: RecoveryEventCategory | None,
        status: RecoveryEventStatus | None,
    ) -> None:
        """Event検索条件の型を検証する。"""

        if source is not None and not isinstance(
            source,
            RecoverySource,
        ):
            raise TypeError(
                "source must be a RecoverySource or None"
            )

        if category is not None and not isinstance(
            category,
            RecoveryEventCategory,
        ):
            raise TypeError(
                "category must be a "
                "RecoveryEventCategory or None"
            )

        if status is not None and not isinstance(
            status,
            RecoveryEventStatus,
        ):
            raise TypeError(
                "status must be a "
                "RecoveryEventStatus or None"
            )