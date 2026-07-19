"""Kill Switchに関するドメインモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class KillSwitchStatus(StrEnum):
    """Kill Switchの状態。"""

    ACTIVE = "active"
    BLOCKED = "blocked"

    @property
    def allows_new_entries(self) -> bool:
        return self is KillSwitchStatus.ACTIVE


class KillSwitchReason(StrEnum):
    """停止理由。"""

    NONE = "none"
    MANUAL = "manual"
    DAILY_LOSS = "daily_loss"
    CONSECUTIVE_LOSS = "consecutive_loss"
    RUNTIME_HEALTH = "runtime_health"
    HEARTBEAT = "heartbeat"
    BROKER = "broker"


@dataclass(frozen=True, slots=True)
class KillSwitchSnapshot:
    """Kill Switch判定入力。"""

    manual_blocked: bool = False
    daily_loss_blocked: bool = False
    consecutive_loss_blocked: bool = False
    runtime_health_ok: bool = True
    heartbeat_alive: bool = True
    broker_available: bool = True
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            object.__setattr__(
                self,
                "evaluated_at",
                self.evaluated_at.replace(
                    tzinfo=timezone.utc,
                ),
            )
        else:
            object.__setattr__(
                self,
                "evaluated_at",
                self.evaluated_at.astimezone(
                    timezone.utc,
                ),
            )


@dataclass(frozen=True, slots=True)
class KillSwitchEvaluation:
    """Kill Switch判定結果。"""

    status: KillSwitchStatus
    reason: KillSwitchReason
    evaluated_at: datetime
    metadata: dict[str, object] | None = None

    @property
    def allows_new_entries(self) -> bool:
        return self.status.allows_new_entries

    @property
    def is_blocked(self) -> bool:
        return self.status is KillSwitchStatus.BLOCKED