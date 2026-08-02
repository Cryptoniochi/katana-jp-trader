"""KATANA Service Readiness通知のテスト。"""

from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.run_katana_service import (
    build_readiness_change_handler,
)


class FakeGateway:
    def __init__(self) -> None:
        self.requests = []

    def send(
        self,
        request,
        *,
        continue_on_error,
    ):
        self.requests.append(
            (request, continue_on_error)
        )
        return object()


def test_connected_transition_sends_info_notification(
) -> None:
    gateway = FakeGateway()
    handler = build_readiness_change_handler(
        gateway
    )

    assert handler is not None
    handler(
        "disconnected",
        "connected",
        "connected",
    )

    request, continue_on_error = gateway.requests[0]

    assert continue_on_error
    assert request.severity is (
        NotificationSeverity.INFO
    )
    assert request.metadata[
        "current_state"
    ] == "connected"


def test_disconnected_transition_sends_critical_notification(
) -> None:
    gateway = FakeGateway()
    handler = build_readiness_change_handler(
        gateway
    )

    assert handler is not None
    handler(
        "connected",
        "disconnected",
        "token failed",
    )

    request, _ = gateway.requests[0]

    assert request.severity is (
        NotificationSeverity.CRITICAL
    )
    assert (
        "Paper Tradingを開始しないでください"
        in request.context["message"]
    )
