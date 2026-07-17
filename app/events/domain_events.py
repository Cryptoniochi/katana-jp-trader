"""Project KATANAの軽量Domain Eventモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DomainEventType(StrEnum):
    """Domain Eventの種別。"""

    SIGNAL_CREATED = "signal_created"
    RISK_ASSESSED = "risk_assessed"
    ORDER_CREATED = "order_created"
    ORDER_UPDATED = "order_updated"
    EXECUTION_RECORDED = "execution_recorded"
    PORTFOLIO_UPDATED = "portfolio_updated"
    RECOVERY_COMPLETED = "recovery_completed"
    ERROR_OCCURRED = "error_occurred"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Event Busで配信する共通イベント。"""

    event_id: str
    event_type: DomainEventType
    occurred_at: datetime
    source: str
    payload: dict[str, Any] = field(
        default_factory=dict,
    )
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        """イベント内容を検証して正規化する。"""

        event_id = self.event_id.strip()
        source = self.source.strip()
        correlation_id = (
            None
            if self.correlation_id is None
            else self.correlation_id.strip()
        )

        if not event_id:
            raise ValueError(
                "イベントIDを指定してください。"
            )

        if not source:
            raise ValueError(
                "イベント発生元を指定してください。"
            )

        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "イベント発生日時にはタイムゾーンが必要です。"
            )

        if not isinstance(self.payload, dict):
            raise TypeError(
                "イベントPayloadは辞書形式で指定してください。"
            )

        object.__setattr__(
            self,
            "event_id",
            event_id,
        )
        object.__setattr__(
            self,
            "source",
            source,
        )
        object.__setattr__(
            self,
            "payload",
            dict(self.payload),
        )
        object.__setattr__(
            self,
            "correlation_id",
            correlation_id or None,
        )
