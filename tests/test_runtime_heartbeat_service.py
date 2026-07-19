"""RuntimeHeartbeatServiceのテスト。"""

from datetime import datetime, timedelta, timezone
from threading import Thread

import pytest

from app.runtime.runtime_heartbeat_models import (
    RuntimeHeartbeat,
    RuntimeHeartbeatStatus,
)
from app.runtime.runtime_heartbeat_service import (
    RuntimeHeartbeatService,
)


NOW = datetime(
    2026,
    7,
    19,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_initial_snapshot_is_missing() -> None:
    """Heartbeat未記録時はMISSINGを返す。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    snapshot = service.snapshot()

    assert snapshot.status is RuntimeHeartbeatStatus.MISSING
    assert snapshot.last_heartbeat is None
    assert snapshot.age is None
    assert not snapshot.is_alive
    assert snapshot.requires_attention


def test_beat_records_first_heartbeat() -> None:
    """最初のHeartbeatをsequence=1で記録する。"""

    service = RuntimeHeartbeatService(
        source="runtime-a",
        now_provider=lambda: NOW,
    )

    heartbeat = service.beat(
        details={
            "cycle_count": 3,
        }
    )

    assert heartbeat.sequence == 1
    assert heartbeat.recorded_at == NOW
    assert heartbeat.source == "runtime-a"
    assert heartbeat.details == {
        "cycle_count": 3,
    }
    assert service.last_heartbeat == heartbeat
    assert service.next_sequence == 2


def test_beat_increments_sequence() -> None:
    """Heartbeatごとにsequenceを加算する。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    first = service.beat()
    second = service.beat(
        recorded_at=NOW + timedelta(seconds=1)
    )
    third = service.beat(
        recorded_at=NOW + timedelta(seconds=2)
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert third.sequence == 3
    assert service.next_sequence == 4


def test_snapshot_is_alive_before_stale_threshold() -> None:
    """失効閾値未満ならALIVEを返す。"""

    service = RuntimeHeartbeatService(
        stale_after=timedelta(minutes=2),
        now_provider=lambda: NOW,
    )
    heartbeat = service.beat()

    snapshot = service.snapshot(
        checked_at=NOW + timedelta(
            minutes=1,
            seconds=59,
        )
    )

    assert snapshot.status is RuntimeHeartbeatStatus.ALIVE
    assert snapshot.last_heartbeat == heartbeat
    assert snapshot.age == timedelta(
        minutes=1,
        seconds=59,
    )
    assert snapshot.is_alive
    assert not snapshot.requires_attention


def test_snapshot_is_stale_at_threshold() -> None:
    """失効閾値と同時刻ならSTALEを返す。"""

    service = RuntimeHeartbeatService(
        stale_after=timedelta(minutes=2),
        now_provider=lambda: NOW,
    )
    service.beat()

    snapshot = service.snapshot(
        checked_at=NOW + timedelta(minutes=2)
    )

    assert snapshot.status is RuntimeHeartbeatStatus.STALE
    assert snapshot.age == timedelta(minutes=2)
    assert not snapshot.is_alive
    assert snapshot.requires_attention


def test_is_alive_delegates_to_snapshot() -> None:
    """is_aliveが現在のHeartbeat判定を返す。"""

    service = RuntimeHeartbeatService(
        stale_after=timedelta(minutes=2),
        now_provider=lambda: NOW,
    )
    service.beat()

    assert service.is_alive(
        checked_at=NOW + timedelta(minutes=1)
    )
    assert not service.is_alive(
        checked_at=NOW + timedelta(minutes=2)
    )


def test_reset_clears_state_and_sequence() -> None:
    """resetでHeartbeatとsequenceを初期化する。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )
    service.beat()
    service.beat(
        recorded_at=NOW + timedelta(seconds=1)
    )

    service.reset()

    assert service.last_heartbeat is None
    assert service.next_sequence == 1
    assert (
        service.snapshot().status
        is RuntimeHeartbeatStatus.MISSING
    )


def test_restore_recovers_last_heartbeat_and_sequence() -> None:
    """restoreで最新Heartbeatと次sequenceを復元する。"""

    restored = RuntimeHeartbeat(
        sequence=15,
        recorded_at=NOW,
        source="restored-runtime",
        details={
            "restored": True,
        },
    )
    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    service.restore(
        last_heartbeat=restored,
    )

    assert service.last_heartbeat == restored
    assert service.next_sequence == 16

    next_heartbeat = service.beat(
        recorded_at=NOW + timedelta(seconds=1)
    )

    assert next_heartbeat.sequence == 16
    assert next_heartbeat.source == service.source


def test_restore_none_resets_sequence() -> None:
    """None復元時は初期状態へ戻す。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )
    service.beat()

    service.restore(
        last_heartbeat=None,
    )

    assert service.last_heartbeat is None
    assert service.next_sequence == 1


def test_details_are_copied() -> None:
    """呼び出し元のdetails変更がHeartbeatへ波及しない。"""

    details = {
        "cycle_count": 1,
    }
    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    heartbeat = service.beat(
        details=details,
    )
    details["cycle_count"] = 99

    assert heartbeat.details == {
        "cycle_count": 1,
    }


def test_recorded_at_is_normalized_to_utc() -> None:
    """Heartbeat日時をUTCへ正規化する。"""

    jst = timezone(timedelta(hours=9))
    recorded_at = datetime(
        2026,
        7,
        19,
        9,
        0,
        tzinfo=jst,
    )
    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    heartbeat = service.beat(
        recorded_at=recorded_at,
    )

    assert heartbeat.recorded_at == NOW
    assert heartbeat.recorded_at.tzinfo is timezone.utc


def test_constructor_rejects_blank_source() -> None:
    """空白sourceを拒否する。"""

    with pytest.raises(ValueError, match="source"):
        RuntimeHeartbeatService(
            source="   ",
        )


def test_constructor_rejects_non_positive_stale_after() -> None:
    """0以下の失効閾値を拒否する。"""

    with pytest.raises(ValueError, match="stale_after"):
        RuntimeHeartbeatService(
            stale_after=timedelta(0),
        )

    with pytest.raises(ValueError, match="stale_after"):
        RuntimeHeartbeatService(
            stale_after=timedelta(seconds=-1),
        )


def test_beat_rejects_naive_recorded_at() -> None:
    """タイムゾーンなし記録日時を拒否する。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.beat(
            recorded_at=datetime(
                2026,
                7,
                19,
                0,
                0,
            )
        )


def test_snapshot_rejects_naive_checked_at() -> None:
    """タイムゾーンなし確認日時を拒否する。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.snapshot(
            checked_at=datetime(
                2026,
                7,
                19,
                0,
                0,
            )
        )


def test_now_provider_must_return_aware_datetime() -> None:
    """時計がタイムゾーンなし日時を返した場合は拒否する。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: datetime(
            2026,
            7,
            19,
            0,
            0,
        )
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.beat()

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.snapshot()


def test_concurrent_beats_assign_unique_sequences() -> None:
    """並行記録でもsequenceが重複しない。"""

    service = RuntimeHeartbeatService(
        now_provider=lambda: NOW,
    )
    recorded_sequences: list[int] = []

    def record_heartbeat() -> None:
        heartbeat = service.beat()
        recorded_sequences.append(
            heartbeat.sequence
        )

    threads = [
        Thread(target=record_heartbeat)
        for _ in range(50)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert sorted(recorded_sequences) == list(
        range(1, 51)
    )
    assert service.next_sequence == 51
    assert service.last_heartbeat is not None
    assert service.last_heartbeat.sequence == 50
