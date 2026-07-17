"""DomainEventBusのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.events.domain_event_bus import (
    DomainEventBus,
    DomainEventDispatchDecision,
)
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


def event(
    event_id: str = "event-1",
    event_type: DomainEventType = (
        DomainEventType.SIGNAL_CREATED
    ),
) -> DomainEvent:
    """テスト用Domain Eventを作成する。"""

    return DomainEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=NOW,
        source="test",
    )


def test_publish_calls_handlers_in_registration_order() -> None:
    """登録順に同期配信する。"""

    bus = DomainEventBus()
    calls: list[str] = []

    def first(_event: DomainEvent) -> None:
        calls.append("first")

    def second(_event: DomainEvent) -> None:
        calls.append("second")

    bus.subscribe(
        DomainEventType.SIGNAL_CREATED,
        first,
    )
    bus.subscribe(
        DomainEventType.SIGNAL_CREATED,
        second,
    )

    result = bus.publish(event())

    assert calls == ["first", "second"]
    assert result.is_successful
    assert result.handler_count == 2
    assert result.succeeded_count == 2


def test_duplicate_subscription_is_rejected() -> None:
    """同じハンドラーの重複登録を防止する。"""

    bus = DomainEventBus()

    def handler(_event: DomainEvent) -> None:
        pass

    assert bus.subscribe(
        DomainEventType.ORDER_CREATED,
        handler,
    )
    assert bus.subscribe(
        DomainEventType.ORDER_CREATED,
        handler,
    ) is False
    assert bus.subscriber_count(
        DomainEventType.ORDER_CREATED
    ) == 1


def test_unsubscribe_removes_handler() -> None:
    """購読解除後はハンドラーを呼ばない。"""

    bus = DomainEventBus()
    calls: list[str] = []

    def handler(_event: DomainEvent) -> None:
        calls.append("called")

    bus.subscribe(
        DomainEventType.ORDER_UPDATED,
        handler,
    )

    assert bus.unsubscribe(
        DomainEventType.ORDER_UPDATED,
        handler,
    )
    assert bus.unsubscribe(
        DomainEventType.ORDER_UPDATED,
        handler,
    ) is False

    result = bus.publish(
        event(
            event_type=DomainEventType.ORDER_UPDATED
        )
    )

    assert calls == []
    assert result.handler_count == 0
    assert result.is_successful


def test_publish_continues_after_handler_error() -> None:
    """継続モードでは後続ハンドラーを実行する。"""

    bus = DomainEventBus()
    calls: list[str] = []

    def failing(_event: DomainEvent) -> None:
        raise RuntimeError("handler failed")

    def succeeding(_event: DomainEvent) -> None:
        calls.append("succeeded")

    bus.subscribe(
        DomainEventType.EXECUTION_RECORDED,
        failing,
    )
    bus.subscribe(
        DomainEventType.EXECUTION_RECORDED,
        succeeding,
    )

    result = bus.publish(
        event(
            event_type=(
                DomainEventType.EXECUTION_RECORDED
            )
        ),
        continue_on_error=True,
    )

    assert calls == ["succeeded"]
    assert result.decision is (
        DomainEventDispatchDecision
        .COMPLETED_WITH_ERRORS
    )
    assert result.succeeded_count == 1
    assert len(result.errors) == 1
    assert result.errors[0].error_message == (
        "handler failed"
    )


def test_publish_raises_when_not_continuing() -> None:
    """停止モードではハンドラー例外を送出する。"""

    bus = DomainEventBus()

    def failing(_event: DomainEvent) -> None:
        raise RuntimeError("stop dispatch")

    bus.subscribe(
        DomainEventType.ERROR_OCCURRED,
        failing,
    )

    with pytest.raises(
        RuntimeError,
        match="stop dispatch",
    ):
        bus.publish(
            event(
                event_type=DomainEventType.ERROR_OCCURRED
            ),
            continue_on_error=False,
        )


def test_all_handlers_failed_returns_failed() -> None:
    """全ハンドラー失敗時はFAILEDを返す。"""

    bus = DomainEventBus()

    def failing(_event: DomainEvent) -> None:
        raise RuntimeError("failed")

    bus.subscribe(
        DomainEventType.RISK_ASSESSED,
        failing,
    )

    result = bus.publish(
        event(
            event_type=DomainEventType.RISK_ASSESSED
        )
    )

    assert result.decision is (
        DomainEventDispatchDecision.FAILED
    )
    assert result.succeeded_count == 0
    assert len(result.errors) == 1


def test_history_respects_limit_and_filter() -> None:
    """履歴上限とイベント種別フィルターを適用する。"""

    bus = DomainEventBus(history_limit=2)

    bus.publish(event("event-1"))
    bus.publish(
        event(
            "event-2",
            DomainEventType.ORDER_CREATED,
        )
    )
    bus.publish(event("event-3"))

    assert [
        item.event_id
        for item in bus.history()
    ] == ["event-2", "event-3"]
    assert [
        item.event_id
        for item in bus.history(
            event_type=DomainEventType.SIGNAL_CREATED
        )
    ] == ["event-3"]

    bus.clear_history()
    assert bus.history() == ()


def test_history_can_be_disabled() -> None:
    """履歴上限0で履歴保存を無効化する。"""

    bus = DomainEventBus(history_limit=0)
    bus.publish(event())

    assert bus.history() == ()


def test_bus_rejects_invalid_settings_and_handler() -> None:
    """不正な設定とハンドラーを拒否する。"""

    with pytest.raises(ValueError, match="履歴上限"):
        DomainEventBus(history_limit=-1)

    bus = DomainEventBus()

    with pytest.raises(TypeError, match="呼び出し可能"):
        bus.subscribe(
            DomainEventType.SIGNAL_CREATED,
            object(),  # type: ignore[arg-type]
        )
