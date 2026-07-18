"""Runtimeの稼働継続性を判定する共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RuntimeHealthStatus(StrEnum):
    """Runtime稼働継続性の状態。"""

    IDLE = "idle"
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class RuntimeHealthMonitorPolicy:
    """Heartbeat・Cycle停滞判定の閾値。"""

    heartbeat_warning_seconds: float = 90.0
    heartbeat_critical_seconds: float = 180.0
    cycle_warning_seconds: float = 180.0
    cycle_critical_seconds: float = 300.0

    def __post_init__(self) -> None:
        """閾値の範囲と大小関係を検証する。"""

        values = {
            "Heartbeat警告秒数": self.heartbeat_warning_seconds,
            "Heartbeat重大秒数": self.heartbeat_critical_seconds,
            "Cycle警告秒数": self.cycle_warning_seconds,
            "Cycle重大秒数": self.cycle_critical_seconds,
        }

        for name, value in values.items():
            if value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        if (
            self.heartbeat_critical_seconds
            < self.heartbeat_warning_seconds
        ):
            raise ValueError(
                "Heartbeat重大秒数は警告秒数以上である必要があります。"
            )

        if (
            self.cycle_critical_seconds
            < self.cycle_warning_seconds
        ):
            raise ValueError(
                "Cycle重大秒数は警告秒数以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class RuntimeActivitySnapshot:
    """Runtimeの最新活動時刻。"""

    checked_at: datetime
    running: bool
    started_at: datetime | None
    last_heartbeat_at: datetime | None
    last_cycle_at: datetime | None

    def __post_init__(self) -> None:
        """日時と状態の整合性を検証する。"""

        timestamps = {
            "確認日時": self.checked_at,
            "開始日時": self.started_at,
            "最終Heartbeat日時": self.last_heartbeat_at,
            "最終Cycle日時": self.last_cycle_at,
        }

        for name, value in timestamps.items():
            if value is not None and value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.running and self.started_at is None:
            raise ValueError(
                "稼働中Runtimeには開始日時が必要です。"
            )

        for name, value in {
            "開始日時": self.started_at,
            "最終Heartbeat日時": self.last_heartbeat_at,
            "最終Cycle日時": self.last_cycle_at,
        }.items():
            if value is not None and value > self.checked_at:
                raise ValueError(
                    f"{name}は確認日時以前である必要があります。"
                )


@dataclass(frozen=True, slots=True)
class RuntimeHealthMonitorReport:
    """Runtime稼働継続性の判定結果。"""

    status: RuntimeHealthStatus
    checked_at: datetime
    running: bool
    heartbeat_age_seconds: float | None
    cycle_age_seconds: float | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """判定結果の整合性を検証する。"""

        if self.checked_at.tzinfo is None:
            raise ValueError(
                "確認日時にはタイムゾーンが必要です。"
            )

        for name, value in {
            "Heartbeat経過秒数": self.heartbeat_age_seconds,
            "Cycle経過秒数": self.cycle_age_seconds,
        }.items():
            if value is not None and value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        normalized_reasons = tuple(
            reason.strip()
            for reason in self.reasons
            if reason.strip()
        )

        if (
            self.status is RuntimeHealthStatus.HEALTHY
            and normalized_reasons
        ):
            raise ValueError(
                "正常状態には異常理由を設定できません。"
            )

        if (
            self.status in {
                RuntimeHealthStatus.WARNING,
                RuntimeHealthStatus.CRITICAL,
                RuntimeHealthStatus.STOPPED,
            }
            and not normalized_reasons
        ):
            raise ValueError(
                "異常状態には理由が必要です。"
            )

        object.__setattr__(
            self,
            "reasons",
            normalized_reasons,
        )

    @property
    def requires_attention(self) -> bool:
        """運用者の確認が必要か返す。"""

        return self.status in {
            RuntimeHealthStatus.WARNING,
            RuntimeHealthStatus.CRITICAL,
            RuntimeHealthStatus.STOPPED,
        }
