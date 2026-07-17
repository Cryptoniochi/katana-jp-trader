"""Notification Gatewayモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_request_normalizes_and_copies_values() -> None:
    context = {"message": "hello"}
    metadata = {"code": "7203"}

    request = NotificationGatewayRequest(
        notification_id=" notice-1 ",
        template_name=NotificationTemplateName.GENERIC,
        created_at=NOW,
        source=" test ",
        context=context,
        metadata=metadata,
    )
    context["message"] = "changed"
    metadata["code"] = "6758"

    assert request.notification_id == "notice-1"
    assert request.source == "test"
    assert request.context == {"message": "hello"}
    assert request.metadata == {"code": "7203"}


def test_request_rejects_naive_datetime() -> None:
    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        NotificationGatewayRequest(
            notification_id="notice-1",
            template_name=NotificationTemplateName.GENERIC,
            created_at=datetime(2026, 7, 18),
            source="test",
            context={
                "title": "Title",
                "message": "Body",
            },
        )
