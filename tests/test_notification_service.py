"""NotificationServiceのテスト。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.notifications.notification_channels import (
    FileNotificationChannel,
)
from app.notifications.notification_models import (
    NotificationDeliveryDecision,
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.notification_service import (
    NotificationService,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def message(
    notification_id: str = "notice-1",
) -> NotificationMessage:
    return NotificationMessage(
        notification_id=notification_id,
        title="Test",
        body="Body",
        severity=NotificationSeverity.INFO,
        created_at=NOW,
        source="test",
    )


class FakeChannel:
    def __init__(
        self,
        name: str,
        *,
        fail: bool = False,
    ) -> None:
        self._name = name
        self.fail = fail
        self.messages = []

    @property
    def channel_name(self) -> str:
        return self._name

    def send(self, notification) -> None:
        if self.fail:
            raise RuntimeError(f"{self._name} failed")
        self.messages.append(notification)


def test_deliver_sends_to_all_channels() -> None:
    first = FakeChannel("first")
    second = FakeChannel("second")
    service = NotificationService(
        channels=(first, second)
    )

    result = service.deliver(message())

    assert result.decision is (
        NotificationDeliveryDecision.COMPLETED
    )
    assert result.delivered_count == 2
    assert first.messages
    assert second.messages


def test_deliver_continues_after_failure() -> None:
    failing = FakeChannel("failing", fail=True)
    succeeding = FakeChannel("succeeding")
    service = NotificationService(
        channels=(failing, succeeding)
    )

    result = service.deliver(
        message(),
        continue_on_error=True,
    )

    assert result.decision is (
        NotificationDeliveryDecision
        .COMPLETED_WITH_ERRORS
    )
    assert result.delivered_count == 1
    assert result.failed_count == 1


def test_deliver_raises_when_not_continuing() -> None:
    service = NotificationService(
        channels=(FakeChannel("failing", fail=True),)
    )

    with pytest.raises(
        RuntimeError,
        match="failing failed",
    ):
        service.deliver(
            message(),
            continue_on_error=False,
        )


def test_duplicate_notification_is_skipped() -> None:
    channel = FakeChannel("channel")
    service = NotificationService(
        channels=(channel,)
    )

    first = service.deliver(message())
    second = service.deliver(message())

    assert first.delivered_count == 1
    assert second.decision is (
        NotificationDeliveryDecision.SKIPPED
    )
    assert len(channel.messages) == 1


def test_clear_deduplication_allows_resend() -> None:
    channel = FakeChannel("channel")
    service = NotificationService(
        channels=(channel,)
    )

    service.deliver(message())
    service.clear_deduplication()
    service.deliver(message())

    assert len(channel.messages) == 2


def test_file_channel_writes_jsonl(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notifications.jsonl"
    channel = FileNotificationChannel(path=path)

    channel.send(message())

    payload = json.loads(
        path.read_text(encoding="utf-8").strip()
    )

    assert payload["notification_id"] == "notice-1"
    assert payload["severity"] == "info"
