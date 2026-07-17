"""通知モデルのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.notifications.notification_models import (
    NotificationChannelResult,
    NotificationMessage,
    NotificationSeverity,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def test_notification_message_normalizes_values() -> None:
    payload = {"code": "7203"}

    message = NotificationMessage(
        notification_id=" notice-1 ",
        title=" title ",
        body=" body ",
        severity=NotificationSeverity.INFO,
        created_at=NOW,
        source=" source ",
        metadata=payload,
    )
    payload["code"] = "6758"

    assert message.notification_id == "notice-1"
    assert message.title == "title"
    assert message.body == "body"
    assert message.source == "source"
    assert message.metadata == {"code": "7203"}


def test_notification_message_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="通知ID"):
        NotificationMessage(
            notification_id=" ",
            title="title",
            body="body",
            severity=NotificationSeverity.INFO,
            created_at=NOW,
            source="source",
        )

    with pytest.raises(ValueError, match="タイムゾーン"):
        NotificationMessage(
            notification_id="notice-1",
            title="title",
            body="body",
            severity=NotificationSeverity.INFO,
            created_at=datetime(2026, 7, 17),
            source="source",
        )


def test_channel_result_validates_success_and_failure() -> None:
    success = NotificationChannelResult(
        channel_name="console",
        delivered=True,
    )
    failure = NotificationChannelResult(
        channel_name="file",
        delivered=False,
        error_message="failed",
    )

    assert success.delivered
    assert failure.error_message == "failed"

    with pytest.raises(ValueError):
        NotificationChannelResult(
            channel_name="file",
            delivered=False,
        )
