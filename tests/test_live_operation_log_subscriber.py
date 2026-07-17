"""LiveOperationLogSubscriberのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.live.live_operation_log_models import (
    LiveLogEventType,
    LiveLogLevel,
)
from app.live.live_operation_log_service import (
    LiveOperationLogService,
)
from app.live.live_operation_log_subscriber import (
    LiveOperationLogSubscriber,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def create_event(
    *,
    event_id: str,
    event_type: DomainEventType,
    payload: dict[str, object] | None = None,
) -> DomainEvent:
    """テスト用Domain Eventを作成する。"""

    return DomainEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=NOW,
        source="test-source",
        payload=payload or {},
        correlation_id="flow-1",
    )


def create_subscriber(
    tmp_path: Path,
    *,
    event_types: frozenset[DomainEventType] | None = None,
):
    """Subscriberとログサービスを作成する。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )
    subscriber = LiveOperationLogSubscriber(
        service=service,
        event_types=event_types,
    )
    return subscriber, service


def test_signal_event_is_saved_as_signal_log(
    tmp_path: Path,
) -> None:
    """シグナルイベントをSIGNALログへ変換する。"""

    subscriber, service = create_subscriber(tmp_path)

    subscriber(
        create_event(
            event_id="event-1",
            event_type=DomainEventType.SIGNAL_CREATED,
            payload={
                "message": "signal generated",
                "code": "7203",
                "cycle_number": 2,
            },
        )
    )

    entries = service.read_date(NOW.date())

    assert len(entries) == 1
    assert entries[0].event_type is LiveLogEventType.SIGNAL
    assert entries[0].level is LiveLogLevel.INFO
    assert entries[0].message == "signal generated"
    assert entries[0].code == "7203"
    assert entries[0].cycle_number == 2
    assert entries[0].metadata["event_id"] == "event-1"
    assert entries[0].metadata["correlation_id"] == "flow-1"


def test_risk_halt_is_saved_as_critical(
    tmp_path: Path,
) -> None:
    """リスク停止をCRITICALログへ変換する。"""

    subscriber, service = create_subscriber(tmp_path)

    subscriber(
        create_event(
            event_id="event-2",
            event_type=DomainEventType.RISK_ASSESSED,
            payload={
                "decision": "halted",
                "message": "daily loss limit",
            },
        )
    )

    entry = service.read_date(NOW.date())[0]

    assert entry.event_type is LiveLogEventType.RISK
    assert entry.level is LiveLogLevel.CRITICAL


def test_error_event_maps_severity(
    tmp_path: Path,
) -> None:
    """Errorイベントの重大度をログへ反映する。"""

    subscriber, service = create_subscriber(tmp_path)

    subscriber(
        create_event(
            event_id="event-3",
            event_type=DomainEventType.ERROR_OCCURRED,
            payload={
                "severity": "critical",
                "message": "broker unavailable",
            },
        )
    )

    entry = service.read_date(NOW.date())[0]

    assert entry.event_type is LiveLogEventType.ERROR
    assert entry.level is LiveLogLevel.CRITICAL


def test_recovery_error_is_saved_as_warning(
    tmp_path: Path,
) -> None:
    """エラー付きRecoveryをWARNINGログへ変換する。"""

    subscriber, service = create_subscriber(tmp_path)

    subscriber(
        create_event(
            event_id="event-4",
            event_type=DomainEventType.RECOVERY_COMPLETED,
            payload={
                "has_errors": True,
                "message": "recovery completed with errors",
            },
        )
    )

    entry = service.read_date(NOW.date())[0]

    assert entry.event_type is LiveLogEventType.RUN_COMPLETED
    assert entry.level is LiveLogLevel.WARNING


def test_subscriber_filters_event_types(
    tmp_path: Path,
) -> None:
    """対象外イベントを保存しない。"""

    subscriber, service = create_subscriber(
        tmp_path,
        event_types=frozenset(
            {DomainEventType.ERROR_OCCURRED}
        ),
    )

    subscriber(
        create_event(
            event_id="event-5",
            event_type=DomainEventType.ORDER_CREATED,
        )
    )

    assert service.read_date(NOW.date()) == ()


def test_subscriber_works_with_event_bus(
    tmp_path: Path,
) -> None:
    """Event Busハンドラーとして利用できる。"""

    subscriber, service = create_subscriber(tmp_path)
    bus = DomainEventBus()

    bus.subscribe(
        DomainEventType.EXECUTION_RECORDED,
        subscriber,
    )

    result = bus.publish(
        create_event(
            event_id="event-6",
            event_type=DomainEventType.EXECUTION_RECORDED,
            payload={
                "message": "execution recorded",
                "code": "6758",
            },
        )
    )

    assert result.is_successful
    entry = service.read_date(NOW.date())[0]
    assert entry.event_type is LiveLogEventType.EXECUTION
    assert entry.code == "6758"


def test_invalid_cycle_number_raises(
    tmp_path: Path,
) -> None:
    """不正なサイクル番号を拒否する。"""

    subscriber, _service = create_subscriber(tmp_path)

    with pytest.raises(
        ValueError,
        match="cycle_number",
    ):
        subscriber(
            create_event(
                event_id="event-7",
                event_type=DomainEventType.SIGNAL_CREATED,
                payload={"cycle_number": 0},
            )
        )
