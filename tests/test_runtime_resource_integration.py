"""Runtime Resource統合Serviceのテスト。"""

from datetime import datetime, timezone

from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.runtime.resource_integration import (
    RuntimeResourceIntegrationService,
)
from app.runtime.resource_models import (
    RuntimeResourceSnapshot,
    RuntimeResourceStatus,
    RuntimeResourceThresholds,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
    SupervisorStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def evaluation(
    status: RuntimeResourceStatus,
):
    thresholds = RuntimeResourceThresholds(
        cpu_warning_percent=50.0,
        cpu_critical_percent=90.0,
        rss_warning_bytes=1000,
        rss_critical_bytes=2000,
        thread_warning_count=10,
        thread_critical_count=20,
    )
    cpu = {
        RuntimeResourceStatus.NORMAL: 10.0,
        RuntimeResourceStatus.WARNING: 60.0,
        RuntimeResourceStatus.CRITICAL: 95.0,
    }[status]

    return RuntimeResourceSnapshot(
        sampled_at=NOW,
        cpu_percent=cpu,
        rss_bytes=100,
        vms_bytes=200,
        thread_count=1,
        process_uptime_seconds=3600.0,
    ).evaluate(thresholds)


class FakeMonitor:
    def __init__(self, value) -> None:
        self.value = value

    def sample(self):
        return self.value


class FakeGateway:
    def __init__(self) -> None:
        self.requests = []
        self.continue_on_error_values = []

    def send(
        self,
        request,
        *,
        continue_on_error=True,
    ):
        self.requests.append(request)
        self.continue_on_error_values.append(
            continue_on_error
        )
        return object()


class FakeSupervisor:
    def __init__(self) -> None:
        self.calls = []

    def stop(
        self,
        *,
        reason,
        message=None,
    ) -> SupervisorSnapshot:
        self.calls.append((reason, message))
        return SupervisorSnapshot(
            worker_name="live-worker",
            status=SupervisorStatus.FAILED,
            started_at=NOW,
            checked_at=NOW,
            last_heartbeat_at=NOW,
            last_restart_at=None,
            restart_count=0,
            stop_reason=reason,
            message=message,
        )


def test_normal_resource_requires_no_action() -> None:
    gateway = FakeGateway()
    supervisor = FakeSupervisor()
    service = RuntimeResourceIntegrationService(
        monitor=FakeMonitor(
            evaluation(RuntimeResourceStatus.NORMAL)
        ),
        notification_gateway=gateway,
        supervisor=supervisor,
    )

    result = service.sample_once()

    assert result.notification_sent is False
    assert result.supervisor_stopped is False
    assert gateway.requests == []
    assert supervisor.calls == []


def test_warning_resource_sends_warning_notification() -> None:
    gateway = FakeGateway()
    supervisor = FakeSupervisor()
    service = RuntimeResourceIntegrationService(
        monitor=FakeMonitor(
            evaluation(RuntimeResourceStatus.WARNING)
        ),
        notification_gateway=gateway,
        supervisor=supervisor,
        notification_id_provider=lambda: "resource-1",
    )

    result = service.sample_once(
        continue_on_notification_error=False
    )

    request = gateway.requests[0]

    assert result.notification_sent
    assert result.supervisor_stopped is False
    assert request.notification_id == "resource-1"
    assert request.severity is NotificationSeverity.WARNING
    assert request.metadata["current_status"] == "warning"
    assert request.metadata["cpu_percent"] == 60.0
    assert gateway.continue_on_error_values == [False]
    assert supervisor.calls == []


def test_critical_resource_notifies_and_stops_supervisor() -> None:
    gateway = FakeGateway()
    supervisor = FakeSupervisor()
    service = RuntimeResourceIntegrationService(
        monitor=FakeMonitor(
            evaluation(RuntimeResourceStatus.CRITICAL)
        ),
        notification_gateway=gateway,
        supervisor=supervisor,
        notification_id_provider=lambda: "resource-2",
    )

    result = service.sample_once()

    assert result.notification_sent
    assert result.supervisor_stopped
    assert gateway.requests[0].severity is (
        NotificationSeverity.CRITICAL
    )
    assert supervisor.calls[0][0] is (
        SupervisorStopReason.ERROR
    )
    assert "重大状態" in supervisor.calls[0][1]


def test_critical_can_leave_supervisor_running_by_policy() -> None:
    supervisor = FakeSupervisor()
    service = RuntimeResourceIntegrationService(
        monitor=FakeMonitor(
            evaluation(RuntimeResourceStatus.CRITICAL)
        ),
        supervisor=supervisor,
        stop_supervisor_on_critical=False,
    )

    result = service.sample_once()

    assert result.supervisor_stopped is False
    assert supervisor.calls == []
