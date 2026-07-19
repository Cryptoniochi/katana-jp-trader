"""統合リスクレポートに関するドメインモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any


class RiskReportStatus(StrEnum):
    """統合リスクレポートの総合状態。"""

    CLEAR = "clear"
    WARNING = "warning"
    BLOCKED = "blocked"

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可する状態か返す。"""

        return self is not RiskReportStatus.BLOCKED

    @property
    def is_blocked(self) -> bool:
        """新規エントリー停止状態か返す。"""

        return self is RiskReportStatus.BLOCKED

    @property
    def has_warning(self) -> bool:
        """警告または停止状態か返す。"""

        return self in {
            RiskReportStatus.WARNING,
            RiskReportStatus.BLOCKED,
        }


class RiskReportReason(StrEnum):
    """統合リスクレポートの判定理由。"""

    ALL_CLEAR = "all_clear"
    POSITION_SIZE_REDUCED = "position_size_reduced"
    POSITION_SIZE_REJECTED = "position_size_rejected"
    DAILY_LOSS_WARNING = "daily_loss_warning"
    DAILY_LOSS_BLOCKED = "daily_loss_blocked"
    CONSECUTIVE_LOSS_WARNING = "consecutive_loss_warning"
    CONSECUTIVE_LOSS_BLOCKED = "consecutive_loss_blocked"
    KILL_SWITCH_BLOCKED = "kill_switch_blocked"
    RUNTIME_HEALTH_WARNING = "runtime_health_warning"
    RUNTIME_HEALTH_ERROR = "runtime_health_error"
    HEARTBEAT_STALE = "heartbeat_stale"
    HEARTBEAT_MISSING = "heartbeat_missing"
    BROKER_UNAVAILABLE = "broker_unavailable"


@dataclass(frozen=True, slots=True)
class RiskReportItem:
    """個別リスク判定を表すレポート項目。"""

    name: str
    status: RiskReportStatus
    reason: RiskReportReason
    message: str
    blocks_new_entries: bool = False
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """項目値の整合性を検証して正規化する。"""

        normalized_name = self.name.strip()
        normalized_message = self.message.strip()

        if not normalized_name:
            raise ValueError(
                "nameを指定してください。"
            )

        if not normalized_message:
            raise ValueError(
                "messageを指定してください。"
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "message",
            normalized_message,
        )

        if (
            self.blocks_new_entries
            and self.status is not RiskReportStatus.BLOCKED
        ):
            raise ValueError(
                "blocks_new_entries=Trueの場合、statusはBLOCKEDである必要があります。"
            )

        if (
            self.status is RiskReportStatus.BLOCKED
            and not self.blocks_new_entries
        ):
            raise ValueError(
                "BLOCKED項目はblocks_new_entries=Trueである必要があります。"
            )

        if (
            self.status is RiskReportStatus.CLEAR
            and self.reason is not RiskReportReason.ALL_CLEAR
        ):
            raise ValueError(
                "CLEAR項目のreasonはALL_CLEARである必要があります。"
            )


@dataclass(frozen=True, slots=True)
class RiskReportSnapshot:
    """統合リスクレポート生成時の入力状態。"""

    trading_date: date
    items: tuple[RiskReportItem, ...]
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Snapshot値を検証してUTCへ正規化する。"""

        if not self.items:
            raise ValueError(
                "itemsを1件以上指定してください。"
            )

        names = [
            item.name
            for item in self.items
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "RiskReportItemのnameは重複できません。"
            )

        normalized = self._normalize_datetime(
            self.generated_at
        )
        object.__setattr__(
            self,
            "generated_at",
            normalized,
        )

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """datetimeをUTCへ正規化する。"""

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class RiskReport:
    """複数のリスク判定を集約した統合レポート。"""

    trading_date: date
    status: RiskReportStatus
    primary_reason: RiskReportReason
    items: tuple[RiskReportItem, ...]
    warning_reasons: tuple[RiskReportReason, ...]
    blocking_reasons: tuple[RiskReportReason, ...]
    generated_at: datetime
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """統合レポートの整合性を検証する。"""

        if not self.items:
            raise ValueError(
                "itemsを1件以上指定してください。"
            )

        names = [
            item.name
            for item in self.items
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "RiskReportItemのnameは重複できません。"
            )

        expected_warning_reasons = tuple(
            item.reason
            for item in self.items
            if item.status is RiskReportStatus.WARNING
        )
        expected_blocking_reasons = tuple(
            item.reason
            for item in self.items
            if item.status is RiskReportStatus.BLOCKED
        )

        if self.warning_reasons != expected_warning_reasons:
            raise ValueError(
                "warning_reasonsがitemsのWARNING項目と一致しません。"
            )

        if self.blocking_reasons != expected_blocking_reasons:
            raise ValueError(
                "blocking_reasonsがitemsのBLOCKED項目と一致しません。"
            )

        if self.status is RiskReportStatus.CLEAR:
            if self.primary_reason is not RiskReportReason.ALL_CLEAR:
                raise ValueError(
                    "CLEARのprimary_reasonはALL_CLEARである必要があります。"
                )

            if self.warning_reasons or self.blocking_reasons:
                raise ValueError(
                    "CLEARでは警告理由と停止理由を保持できません。"
                )

        if self.status is RiskReportStatus.WARNING:
            if not self.warning_reasons:
                raise ValueError(
                    "WARNINGにはwarning_reasonsが必要です。"
                )

            if self.blocking_reasons:
                raise ValueError(
                    "WARNINGではblocking_reasonsを保持できません。"
                )

            if self.primary_reason != self.warning_reasons[0]:
                raise ValueError(
                    "WARNINGのprimary_reasonは最初の警告理由と一致する必要があります。"
                )

        if self.status is RiskReportStatus.BLOCKED:
            if not self.blocking_reasons:
                raise ValueError(
                    "BLOCKEDにはblocking_reasonsが必要です。"
                )

            if self.primary_reason != self.blocking_reasons[0]:
                raise ValueError(
                    "BLOCKEDのprimary_reasonは最初の停止理由と一致する必要があります。"
                )

        normalized = RiskReportSnapshot._normalize_datetime(
            self.generated_at
        )
        object.__setattr__(
            self,
            "generated_at",
            normalized,
        )

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.status.allows_new_entries

    @property
    def is_blocked(self) -> bool:
        """新規エントリー停止状態か返す。"""

        return self.status.is_blocked

    @property
    def has_warning(self) -> bool:
        """警告または停止状態か返す。"""

        return self.status.has_warning
