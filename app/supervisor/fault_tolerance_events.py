"""耐障害性フロー結果をDomain Eventとして発行する。"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
)


class FaultToleranceEventPublisher:
    """耐障害性フロー結果を既存Event Busへ発行する。"""

    def __init__(
        self,
        *,
        event_bus: DomainEventBus,
        event_id_provider: Callable[[], str] | None = None,
        source: str = "fault-tolerance",
    ) -> None:
        """Event Bus・ID生成・発生元を設定する。"""

        source = source.strip()

        if not source:
            raise ValueError(
                "イベント発生元を指定してください。"
            )

        self.event_bus = event_bus
        self.event_id_provider = (
            event_id_provider
            if event_id_provider is not None
            else lambda: uuid4().hex
        )
        self.source = source

    def publish(
        self,
        attempt: FaultToleranceAttempt,
        *,
        continue_on_error: bool = True,
    ):
        """耐障害性フロー結果をDomain Eventへ変換する。"""

        event_id = self.event_id_provider().strip()

        if not event_id:
            raise ValueError(
                "イベントIDを生成できませんでした。"
            )

        event = DomainEvent(
            event_id=event_id,
            event_type=DomainEventType.RECOVERY_COMPLETED,
            occurred_at=attempt.checked_at,
            source=self.source,
            correlation_id=(
                "fault-tolerance-"
                f"{attempt.supervisor_before.worker_name}-"
                f"{attempt.attempt_number}"
            ),
            payload={
                "message": attempt.message,
                "has_errors": attempt.requires_attention,
                "severity": self._severity(attempt.decision),
                "decision": attempt.decision.value,
                "attempt_number": attempt.attempt_number,
                "worker_name": (
                    attempt.supervisor_before.worker_name
                ),
                "consecutive_failure_count": (
                    attempt.consecutive_failure_count
                ),
                "supervisor_status_before": (
                    attempt.supervisor_before.status.value
                ),
                "supervisor_status_after": (
                    attempt.supervisor_after.status.value
                ),
                "recovery_status": (
                    attempt.recovery_result.status.value
                    if attempt.recovery_result is not None
                    else None
                ),
                "next_action_at": (
                    attempt.next_action_at.isoformat()
                    if attempt.next_action_at is not None
                    else None
                ),
            },
        )

        return self.event_bus.publish(
            event,
            continue_on_error=continue_on_error,
        )

    @staticmethod
    def _severity(
        decision: FaultToleranceDecision,
    ) -> str:
        """判定結果を通知重大度へ変換する。"""

        if decision is FaultToleranceDecision.SAFE_STOP:
            return "critical"

        if decision is FaultToleranceDecision.RECOVERY_FAILED:
            return "error"

        if decision is FaultToleranceDecision.DEFERRED:
            return "warning"

        return "info"
