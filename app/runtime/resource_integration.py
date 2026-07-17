"""Runtime Resource監視を通知・Supervisorへ接続する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
    NotificationGatewayResult,
)
from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)
from app.runtime.resource_models import (
    RuntimeResourceEvaluation,
    RuntimeResourceStatus,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStopReason,
)


class RuntimeResourceMonitor(Protocol):
    """Resource Integrationが利用する監視処理。"""

    def sample(self) -> RuntimeResourceEvaluation:
        """現在プロセスを1回評価する。"""


class RuntimeResourceNotificationGateway(Protocol):
    """Resource Integrationが利用する通知Gateway。"""

    def send(
        self,
        request: NotificationGatewayRequest,
        *,
        continue_on_error: bool = True,
    ) -> NotificationGatewayResult:
        """通知をルールに従って配信する。"""


class RuntimeResourceSupervisor(Protocol):
    """重大リソース異常時に安全停止するSupervisor。"""

    def stop(
        self,
        *,
        reason: SupervisorStopReason,
        message: str | None = None,
    ) -> SupervisorSnapshot:
        """Supervisorを停止状態へする。"""


@dataclass(frozen=True, slots=True)
class RuntimeResourceIntegrationResult:
    """Resource監視1回分の統合結果。"""

    evaluation: RuntimeResourceEvaluation
    notification_result: NotificationGatewayResult | None
    supervisor_snapshot: SupervisorSnapshot | None

    @property
    def notification_sent(self) -> bool:
        """通知処理が実行されたか返す。"""

        return self.notification_result is not None

    @property
    def supervisor_stopped(self) -> bool:
        """Supervisor停止が実行されたか返す。"""

        return self.supervisor_snapshot is not None


class RuntimeResourceIntegrationService:
    """Resource評価を通知・Supervisorへ反映する。"""

    def __init__(
        self,
        *,
        monitor: RuntimeResourceMonitor,
        notification_gateway: (
            RuntimeResourceNotificationGateway | None
        ) = None,
        supervisor: RuntimeResourceSupervisor | None = None,
        stop_supervisor_on_critical: bool = True,
        notification_id_provider=None,
    ) -> None:
        """依存関係と重大時の動作を設定する。"""

        self.monitor = monitor
        self.notification_gateway = notification_gateway
        self.supervisor = supervisor
        self.stop_supervisor_on_critical = (
            stop_supervisor_on_critical
        )
        self.notification_id_provider = (
            notification_id_provider
            if notification_id_provider is not None
            else lambda: uuid4().hex
        )

    def sample_once(
        self,
        *,
        continue_on_notification_error: bool = True,
    ) -> RuntimeResourceIntegrationResult:
        """Resourceを評価して必要な連携処理を行う。"""

        evaluation = self.monitor.sample()
        notification_result = self._notify(
            evaluation,
            continue_on_error=continue_on_notification_error,
        )
        supervisor_snapshot = self._stop_supervisor(
            evaluation
        )

        return RuntimeResourceIntegrationResult(
            evaluation=evaluation,
            notification_result=notification_result,
            supervisor_snapshot=supervisor_snapshot,
        )

    def _notify(
        self,
        evaluation: RuntimeResourceEvaluation,
        *,
        continue_on_error: bool,
    ) -> NotificationGatewayResult | None:
        """WARNING・CRITICALをNotification Gatewayへ送る。"""

        if (
            self.notification_gateway is None
            or evaluation.status is RuntimeResourceStatus.NORMAL
        ):
            return None

        notification_id = (
            self.notification_id_provider().strip()
        )

        if not notification_id:
            raise ValueError(
                "Resource通知IDを生成できませんでした。"
            )

        severity = (
            NotificationSeverity.CRITICAL
            if evaluation.status
            is RuntimeResourceStatus.CRITICAL
            else NotificationSeverity.WARNING
        )
        snapshot = evaluation.snapshot
        message = " / ".join(evaluation.reasons)

        request = NotificationGatewayRequest(
            notification_id=notification_id,
            template_name=NotificationTemplateName.GENERIC,
            created_at=snapshot.sampled_at,
            source="runtime-resource-monitor",
            context={
                "title": (
                    "Runtime Resource: "
                    f"{evaluation.status.value.upper()}"
                ),
                "message": message,
            },
            severity=severity,
            metadata={
                "current_status": evaluation.status.value,
                "cpu_percent": snapshot.cpu_percent,
                "rss_bytes": snapshot.rss_bytes,
                "vms_bytes": snapshot.vms_bytes,
                "thread_count": snapshot.thread_count,
                "process_uptime_seconds": (
                    snapshot.process_uptime_seconds
                ),
            },
        )

        return self.notification_gateway.send(
            request,
            continue_on_error=continue_on_error,
        )

    def _stop_supervisor(
        self,
        evaluation: RuntimeResourceEvaluation,
    ) -> SupervisorSnapshot | None:
        """重大異常時にSupervisorを安全停止する。"""

        if (
            self.supervisor is None
            or not self.stop_supervisor_on_critical
            or evaluation.status
            is not RuntimeResourceStatus.CRITICAL
        ):
            return None

        return self.supervisor.stop(
            reason=SupervisorStopReason.ERROR,
            message=(
                "Runtime Resourceが重大状態です。 "
                + " / ".join(evaluation.reasons)
            ),
        )
