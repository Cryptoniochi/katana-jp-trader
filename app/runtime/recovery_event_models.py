"""Recoveryサブシステム共通のイベントモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4


class RecoverySource(StrEnum):
    """Recoveryイベントの発生元。"""

    RUNTIME = "runtime"
    LIVE = "live"
    BROKER = "broker"
    SUPERVISOR = "supervisor"


class RecoveryEventCategory(StrEnum):
    """Recoveryイベントの処理分類。"""

    RECOVERY = "recovery"
    RECONNECT = "reconnect"
    RESTART = "restart"
    RECONCILIATION = "reconciliation"
    SNAPSHOT = "snapshot"
    AUDIT = "audit"
    OTHER = "other"


class RecoveryEventStatus(StrEnum):
    """Recoveryイベントの状態。"""

    STARTED = "started"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RecoveryEvent:
    """Recovery処理をサブシステム横断で表す共通イベント。"""

    source: RecoverySource
    category: RecoveryEventCategory
    status: RecoveryEventStatus
    name: str
    started_at: datetime
    completed_at: datetime | None = None
    message: str | None = None
    metadata: Mapping[str, object] = field(
        default_factory=dict
    )
    event_id: str = field(
        default_factory=lambda: uuid4().hex
    )

    def __post_init__(self) -> None:
        """入力値を検証し、不変なイベントへ正規化する。"""

        if not isinstance(self.source, RecoverySource):
            raise TypeError(
                "source must be a RecoverySource"
            )

        if not isinstance(
            self.category,
            RecoveryEventCategory,
        ):
            raise TypeError(
                "category must be a RecoveryEventCategory"
            )

        if not isinstance(
            self.status,
            RecoveryEventStatus,
        ):
            raise TypeError(
                "status must be a RecoveryEventStatus"
            )

        normalized_name = self._normalize_required_text(
            value=self.name,
            name="name",
        )
        normalized_event_id = (
            self._normalize_required_text(
                value=self.event_id,
                name="event_id",
            )
        )
        normalized_message = self._normalize_optional_text(
            value=self.message,
            name="message",
        )

        self._validate_datetime(
            value=self.started_at,
            name="started_at",
        )

        if self.completed_at is not None:
            self._validate_datetime(
                value=self.completed_at,
                name="completed_at",
            )

            if self.completed_at < self.started_at:
                raise ValueError(
                    "completed_at must be greater than or "
                    "equal to started_at"
                )

        self._validate_status_timestamps()
        self._validate_status_message(
            normalized_message
        )

        normalized_metadata = self._normalize_metadata(
            self.metadata
        )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "event_id",
            normalized_event_id,
        )
        object.__setattr__(
            self,
            "message",
            normalized_message,
        )
        object.__setattr__(
            self,
            "metadata",
            normalized_metadata,
        )

    @property
    def is_terminal(self) -> bool:
        """イベントが終了状態か返す。"""

        return self.status in {
            RecoveryEventStatus.SUCCEEDED,
            RecoveryEventStatus.FAILED,
            RecoveryEventStatus.ABORTED,
            RecoveryEventStatus.SKIPPED,
        }

    @property
    def succeeded(self) -> bool:
        """Recoveryが成功したか返す。"""

        return (
            self.status
            is RecoveryEventStatus.SUCCEEDED
        )

    @property
    def failed(self) -> bool:
        """Recoveryが失敗または中断したか返す。"""

        return self.status in {
            RecoveryEventStatus.FAILED,
            RecoveryEventStatus.ABORTED,
        }

    @property
    def duration_seconds(self) -> float | None:
        """完了済みイベントの経過秒数を返す。"""

        if self.completed_at is None:
            return None

        return (
            self.completed_at - self.started_at
        ).total_seconds()

    def metadata_value(
        self,
        key: str,
        default: object = None,
    ) -> object:
        """Metadataから値を取得する。"""

        if not isinstance(key, str):
            raise TypeError("key must be a str")

        normalized_key = key.strip()

        if not normalized_key:
            raise ValueError(
                "key must not be empty"
            )

        return self.metadata.get(
            normalized_key,
            default,
        )

    def _validate_status_timestamps(self) -> None:
        """状態と完了日時の整合性を検証する。"""

        active_statuses = {
            RecoveryEventStatus.STARTED,
            RecoveryEventStatus.RETRYING,
        }

        if (
            self.status in active_statuses
            and self.completed_at is not None
        ):
            raise ValueError(
                "active RecoveryEvent must not have "
                "completed_at"
            )

        if (
            self.status not in active_statuses
            and self.completed_at is None
        ):
            raise ValueError(
                "terminal RecoveryEvent requires "
                "completed_at"
            )

    def _validate_status_message(
        self,
        message: str | None,
    ) -> None:
        """失敗・中断状態のメッセージを検証する。"""

        if (
            self.status
            in {
                RecoveryEventStatus.FAILED,
                RecoveryEventStatus.ABORTED,
            }
            and message is None
        ):
            raise ValueError(
                "failed or aborted RecoveryEvent "
                "requires message"
            )

    @staticmethod
    def _validate_datetime(
        *,
        value: datetime,
        name: str,
    ) -> None:
        """Timezone-awareなdatetimeか検証する。"""

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

    @staticmethod
    def _normalize_required_text(
        *,
        value: str,
        name: str,
    ) -> str:
        """必須文字列を正規化する。"""

        if not isinstance(value, str):
            raise TypeError(
                f"{name} must be a str"
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{name} must not be empty"
            )

        return normalized

    @staticmethod
    def _normalize_optional_text(
        *,
        value: str | None,
        name: str,
    ) -> str | None:
        """任意文字列を正規化する。"""

        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError(
                f"{name} must be a str or None"
            )

        return value.strip() or None

    @classmethod
    def _normalize_metadata(
        cls,
        metadata: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Metadataを検証して読み取り専用化する。"""

        if not isinstance(metadata, Mapping):
            raise TypeError(
                "metadata must be a Mapping"
            )

        normalized: dict[str, object] = {}

        for key, value in metadata.items():
            normalized_key = (
                cls._normalize_required_text(
                    value=key,
                    name="metadata key",
                )
            )

            if normalized_key in normalized:
                raise ValueError(
                    "metadata contains duplicate "
                    f"normalized key: {normalized_key}"
                )

            normalized[normalized_key] = value

        return MappingProxyType(normalized)