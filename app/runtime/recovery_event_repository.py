"""RecoveryEventを保持するインメモリRepository。"""

from __future__ import annotations

from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)


class RecoveryEventRepository:
    """共通RecoveryEventをメモリ上で管理する。"""

    def __init__(self) -> None:
        self._events: list[RecoveryEvent] = []

    def add(
        self,
        event: RecoveryEvent,
    ) -> RecoveryEvent:
        """RecoveryEventを追加する。"""

        self._validate_event(event)

        if self.get_by_id(event.event_id) is not None:
            raise ValueError(
                "RecoveryEvent with the same event_id "
                "already exists"
            )

        self._events.append(event)
        self._sort_events()

        return event

    def list_all(
        self,
    ) -> tuple[RecoveryEvent, ...]:
        """すべてのRecoveryEventを時系列順で返す。"""

        return tuple(self._events)

    def list_by_source(
        self,
        source: RecoverySource,
    ) -> tuple[RecoveryEvent, ...]:
        """指定した発生元のRecoveryEventを返す。"""

        if not isinstance(source, RecoverySource):
            raise TypeError(
                "source must be a RecoverySource"
            )

        return tuple(
            event
            for event in self._events
            if event.source is source
        )

    def list_by_category(
        self,
        category: RecoveryEventCategory,
    ) -> tuple[RecoveryEvent, ...]:
        """指定分類のRecoveryEventを返す。"""

        if not isinstance(
            category,
            RecoveryEventCategory,
        ):
            raise TypeError(
                "category must be a RecoveryEventCategory"
            )

        return tuple(
            event
            for event in self._events
            if event.category is category
        )

    def list_by_status(
        self,
        status: RecoveryEventStatus,
    ) -> tuple[RecoveryEvent, ...]:
        """指定状態のRecoveryEventを返す。"""

        if not isinstance(
            status,
            RecoveryEventStatus,
        ):
            raise TypeError(
                "status must be a RecoveryEventStatus"
            )

        return tuple(
            event
            for event in self._events
            if event.status is status
        )

    def get_by_id(
        self,
        event_id: str,
    ) -> RecoveryEvent | None:
        """Event IDに一致するRecoveryEventを返す。"""

        normalized_event_id = self._normalize_event_id(
            event_id
        )

        for event in self._events:
            if event.event_id == normalized_event_id:
                return event

        return None

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

        events = (
            self._events
            if source is None
            else [
                event
                for event in self._events
                if event.source is source
            ]
        )

        if not events:
            return None

        return events[-1]

    def count(
        self,
        *,
        source: RecoverySource | None = None,
        category: RecoveryEventCategory | None = None,
        status: RecoveryEventStatus | None = None,
    ) -> int:
        """条件に一致するRecoveryEvent件数を返す。"""

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

        return sum(
            1
            for event in self._events
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

    def clear(self) -> None:
        """すべてのRecoveryEventを削除する。"""

        self._events.clear()

    def _sort_events(self) -> None:
        """RecoveryEventを安定した時系列順へ並べる。"""

        self._events.sort(
            key=lambda event: (
                event.started_at,
                (
                    event.completed_at
                    if event.completed_at is not None
                    else event.started_at
                ),
                event.event_id,
            )
        )

    @staticmethod
    def _validate_event(
        event: RecoveryEvent,
    ) -> None:
        """RecoveryEvent型を検証する。"""

        if not isinstance(event, RecoveryEvent):
            raise TypeError(
                "event must be a RecoveryEvent"
            )

    @staticmethod
    def _normalize_event_id(
        event_id: str,
    ) -> str:
        """Event IDを検証して正規化する。"""

        if not isinstance(event_id, str):
            raise TypeError(
                "event_id must be a str"
            )

        normalized = event_id.strip()

        if not normalized:
            raise ValueError(
                "event_id must not be empty"
            )

        return normalized