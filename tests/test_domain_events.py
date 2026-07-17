"""DomainEventモデルのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def test_domain_event_normalizes_values() -> None:
    """文字列とPayloadを安全に正規化する。"""

    payload = {"code": "7203"}

    event = DomainEvent(
        event_id=" event-1 ",
        event_type=DomainEventType.SIGNAL_CREATED,
        occurred_at=NOW,
        source=" signal-engine ",
        payload=payload,
        correlation_id=" order-flow-1 ",
    )
    payload["code"] = "6758"

    assert event.event_id == "event-1"
    assert event.source == "signal-engine"
    assert event.correlation_id == "order-flow-1"
    assert event.payload == {"code": "7203"}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "event_id": " ",
                "source": "source",
                "occurred_at": NOW,
            },
            "イベントID",
        ),
        (
            {
                "event_id": "event-1",
                "source": " ",
                "occurred_at": NOW,
            },
            "発生元",
        ),
        (
            {
                "event_id": "event-1",
                "source": "source",
                "occurred_at": datetime(2026, 7, 17),
            },
            "タイムゾーン",
        ),
    ],
)
def test_domain_event_rejects_invalid_values(
    kwargs,
    message: str,
) -> None:
    """イベント必須値の不正を拒否する。"""

    with pytest.raises(ValueError, match=message):
        DomainEvent(
            event_type=DomainEventType.ERROR_OCCURRED,
            **kwargs,
        )


def test_domain_event_rejects_non_dict_payload() -> None:
    """辞書以外のPayloadを拒否する。"""

    with pytest.raises(TypeError, match="辞書"):
        DomainEvent(
            event_id="event-1",
            event_type=DomainEventType.ERROR_OCCURRED,
            occurred_at=NOW,
            source="test",
            payload=[],  # type: ignore[arg-type]
        )


def test_all_required_event_types_exist() -> None:
    """主要Domain Event種別を公開する。"""

    assert {
        event_type.value
        for event_type in DomainEventType
    } == {
        "signal_created",
        "risk_assessed",
        "order_created",
        "order_updated",
        "execution_recorded",
        "portfolio_updated",
        "recovery_completed",
        "error_occurred",
    }
