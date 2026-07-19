"""Trading RuntimeのHeartbeatモデル。"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any


class RuntimeHeartbeatStatus(StrEnum):
    """Heartbeatの判定状態。"""

    ALIVE = "alive"
    STALE = "stale"
    MISSING = "missing"

    @property
    def is_alive(
        self,
    ) -> bool:
        """Heartbeatが有効か返す。"""

        return self is RuntimeHeartbeatStatus.ALIVE

    @property
    def requires_attention(
        self,
    ) -> bool:
        """監視上の確認が必要か返す。"""

        return self in {
            RuntimeHeartbeatStatus.STALE,
            RuntimeHeartbeatStatus.MISSING,
        }


@dataclass(frozen=True, slots=True)
class RuntimeHeartbeat:
    """1回分のRuntime Heartbeat。"""

    sequence: int
    recorded_at: datetime
    source: str = "paper_trading_runtime"
    details: dict[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """Heartbeatの値を検証して正規化する。"""

        if self.sequence < 1:
            raise ValueError(
                "Heartbeat sequenceは1以上である必要があります。"
            )

        if self.recorded_at.tzinfo is None:
            raise ValueError(
                "Heartbeat記録日時にはタイムゾーンが必要です。"
            )

        normalized_source = self.source.strip()

        if not normalized_source:
            raise ValueError(
                "Heartbeat sourceを指定してください。"
            )

        object.__setattr__(
            self,
            "recorded_at",
            self.recorded_at.astimezone(
                timezone.utc,
            ),
        )
        object.__setattr__(
            self,
            "source",
            normalized_source,
        )
        object.__setattr__(
            self,
            "details",
            dict(self.details),
        )


@dataclass(frozen=True, slots=True)
class RuntimeHeartbeatSnapshot:
    """Heartbeat監視時点の判定結果。"""

    status: RuntimeHeartbeatStatus
    checked_at: datetime
    last_heartbeat: RuntimeHeartbeat | None
    age: timedelta | None
    stale_after: timedelta

    def __post_init__(self) -> None:
        """判定結果の整合性を検証する。"""

        if self.checked_at.tzinfo is None:
            raise ValueError(
                "Heartbeat確認日時にはタイムゾーンが必要です。"
            )

        if self.stale_after <= timedelta(0):
            raise ValueError(
                "Heartbeat stale_afterは0より大きい必要があります。"
            )

        normalized_checked_at = self.checked_at.astimezone(
            timezone.utc
        )

        if self.last_heartbeat is None:
            if self.status is not RuntimeHeartbeatStatus.MISSING:
                raise ValueError(
                    "Heartbeatが存在しない場合はMISSINGである必要があります。"
                )

            if self.age is not None:
                raise ValueError(
                    "Heartbeatが存在しない場合、ageはNoneである必要があります。"
                )
        else:
            if self.age is None:
                raise ValueError(
                    "Heartbeatが存在する場合、ageが必要です。"
                )

            expected_age = (
                normalized_checked_at
                - self.last_heartbeat.recorded_at
            )

            if self.age != expected_age:
                raise ValueError(
                    "Heartbeat ageが記録日時と一致しません。"
                )

            expected_status = (
                RuntimeHeartbeatStatus.STALE
                if expected_age >= self.stale_after
                else RuntimeHeartbeatStatus.ALIVE
            )

            if self.status is not expected_status:
                raise ValueError(
                    "Heartbeat状態が経過時間と一致しません。 "
                    f"expected={expected_status.value} "
                    f"actual={self.status.value}"
                )

        object.__setattr__(
            self,
            "checked_at",
            normalized_checked_at,
        )

    @classmethod
    def create(
        cls,
        *,
        checked_at: datetime,
        last_heartbeat: RuntimeHeartbeat | None,
        stale_after: timedelta,
    ) -> "RuntimeHeartbeatSnapshot":
        """Heartbeatから監視スナップショットを生成する。"""

        if checked_at.tzinfo is None:
            raise ValueError(
                "Heartbeat確認日時にはタイムゾーンが必要です。"
            )

        normalized_checked_at = checked_at.astimezone(
            timezone.utc
        )

        if last_heartbeat is None:
            return cls(
                status=RuntimeHeartbeatStatus.MISSING,
                checked_at=normalized_checked_at,
                last_heartbeat=None,
                age=None,
                stale_after=stale_after,
            )

        age = (
            normalized_checked_at
            - last_heartbeat.recorded_at
        )
        status = (
            RuntimeHeartbeatStatus.STALE
            if age >= stale_after
            else RuntimeHeartbeatStatus.ALIVE
        )

        return cls(
            status=status,
            checked_at=normalized_checked_at,
            last_heartbeat=last_heartbeat,
            age=age,
            stale_after=stale_after,
        )

    @property
    def is_alive(
        self,
    ) -> bool:
        """RuntimeがHeartbeat上生存しているか返す。"""

        return self.status.is_alive

    @property
    def requires_attention(
        self,
    ) -> bool:
        """監視上の対応が必要か返す。"""

        return self.status.requires_attention
