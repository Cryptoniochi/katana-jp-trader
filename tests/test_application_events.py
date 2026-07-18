"""ApplicationEventPublisherのテスト。"""

from datetime import datetime, timezone

from app.application.application_component import (
    ApplicationComponentRegistration,
)
from app.application.application_events import (
    ApplicationEventPublisher,
)
from app.application.application_models import (
    ApplicationStopReason,
)
from app.application.application_orchestrator import (
    ApplicationOrchestrator,
)
from app.application.application_runner import (
    ApplicationRunner,
)
from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import DomainEventType


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeComponent:
    """Lifecycle Eventテスト用Component。"""

    @property
    def component_name(self) -> str:
        return "runtime-session"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def orchestrator() -> ApplicationOrchestrator:
    """テスト用Orchestratorを作成する。"""

    return ApplicationOrchestrator(
        runner=ApplicationRunner(
            now_provider=lambda: NOW,
        ),
        registrations=(
            ApplicationComponentRegistration(
                component=FakeComponent(),
                start_order=1,
            ),
        ),
    )


def test_publisher_emits_started_event() -> None:
    bus = DomainEventBus()
    received = []
    bus.subscribe(
        DomainEventType.RECOVERY_COMPLETED,
        received.append,
    )
    publisher = ApplicationEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "application-event-1",
    )
    result = orchestrator().start()

    publish_result = publisher.publish_started(result)

    assert publish_result.is_successful
    assert len(received) == 1
    event = received[0]
    assert event.event_id == "application-event-1"
    assert event.event_type is (
        DomainEventType.RECOVERY_COMPLETED
    )
    assert event.payload["lifecycle_action"] == "started"
    assert event.payload["application_state"] == "running"
    assert event.payload["has_errors"] is False
    assert event.payload["components"][0][
        "component_name"
    ] == "runtime-session"


def test_publisher_emits_stopped_event() -> None:
    bus = DomainEventBus()
    received = []
    bus.subscribe(
        DomainEventType.RECOVERY_COMPLETED,
        received.append,
    )
    publisher = ApplicationEventPublisher(
        event_bus=bus,
        event_id_provider=lambda: "application-event-2",
    )
    value = orchestrator()
    value.start()
    result = value.shutdown(
        reason=ApplicationStopReason.NORMAL
    )

    publisher.publish_stopped(result)

    assert received[0].payload[
        "lifecycle_action"
    ] == "stopped"
    assert received[0].payload[
        "application_state"
    ] == "stopped"
    assert received[0].correlation_id == (
        "application-lifecycle"
    )
