"""Phase 6-C read-only runtime safety bridge tests."""

from datetime import datetime, timedelta, timezone

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_runtime_operational_state import (
    KabuStationBrokerAvailabilityProvider,
    RuntimeHealthOkProvider,
    RuntimeSessionActivityProvider,
    RuntimeSessionHeartbeatAliveProvider,
)
from app.runtime.runtime_health_monitor_service import RuntimeHealthMonitorService
from app.runtime.session_service import RuntimeSessionService

NOW = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)


def _session():
    return RuntimeSessionService(now_provider=lambda: NOW, session_id_provider=lambda: "session-test")


def _broker_snapshot(**overrides):
    values = dict(
        generated_at=NOW, state="complete", connected=True, token_issued=True,
        cash_wallet={}, margin_wallet={}, positions=(), orders=(), errors=(),
    )
    values.update(overrides)
    return KabuStationReadOnlySnapshot(**values)


def test_activity_provider_reads_running_session_without_mutation():
    session = _session()
    session.start()
    before = session.snapshot()
    activity = RuntimeSessionActivityProvider(session_service=session, now_provider=lambda: NOW)()
    after = session.snapshot()
    assert activity.running is True
    assert activity.started_at == before.started_at
    assert activity.last_heartbeat_at == before.last_heartbeat_at
    assert activity.last_cycle_at == before.last_cycle_at
    assert after == before


def test_runtime_health_is_not_healthy_before_activity():
    session = _session()
    session.start()
    provider = RuntimeHealthOkProvider(
        activity_provider=RuntimeSessionActivityProvider(session_service=session, now_provider=lambda: NOW),
        monitor=RuntimeHealthMonitorService(),
    )
    assert provider() is False


def test_runtime_health_becomes_healthy_after_cycle_and_heartbeat():
    session = _session()
    session.start()
    session.record_cycle(successful=True)
    session.record_heartbeat()
    provider = RuntimeHealthOkProvider(
        activity_provider=RuntimeSessionActivityProvider(session_service=session, now_provider=lambda: NOW)
    )
    assert provider() is True


def test_heartbeat_missing_is_blocked():
    session = _session()
    session.start()
    assert RuntimeSessionHeartbeatAliveProvider(session_service=session, now_provider=lambda: NOW)() is False


def test_fresh_heartbeat_is_alive_without_recording_new_one():
    session = _session()
    session.start()
    session.record_heartbeat()
    before = session.snapshot()
    provider = RuntimeSessionHeartbeatAliveProvider(
        session_service=session, now_provider=lambda: NOW + timedelta(seconds=30)
    )
    assert provider() is True
    assert session.snapshot() == before


def test_stale_heartbeat_is_blocked():
    session = _session()
    session.start()
    session.record_heartbeat()
    provider = RuntimeSessionHeartbeatAliveProvider(
        session_service=session, stale_after_seconds=180,
        now_provider=lambda: NOW + timedelta(seconds=180),
    )
    assert provider() is False


def test_future_heartbeat_is_blocked():
    session = _session()
    session.start()
    session.record_heartbeat()
    provider = RuntimeSessionHeartbeatAliveProvider(
        session_service=session, now_provider=lambda: NOW - timedelta(seconds=1)
    )
    assert provider() is False


def test_complete_fresh_broker_snapshot_is_available():
    provider = KabuStationBrokerAvailabilityProvider(
        snapshot_provider=lambda: _broker_snapshot(), now_provider=lambda: NOW
    )
    assert provider() is True


def test_missing_broker_snapshot_is_blocked():
    provider = KabuStationBrokerAvailabilityProvider(
        snapshot_provider=lambda: None, now_provider=lambda: NOW
    )
    assert provider() is False


def test_partial_broker_snapshot_is_blocked():
    provider = KabuStationBrokerAvailabilityProvider(
        snapshot_provider=lambda: _broker_snapshot(
            state="partial", connected=False, errors=("positions: failed",)
        ),
        now_provider=lambda: NOW,
    )
    assert provider() is False


def test_stale_broker_snapshot_is_blocked():
    provider = KabuStationBrokerAvailabilityProvider(
        snapshot_provider=lambda: _broker_snapshot(
            generated_at=NOW - timedelta(seconds=121)
        ),
        maximum_age_seconds=120, now_provider=lambda: NOW,
    )
    assert provider() is False


def test_far_future_broker_snapshot_is_blocked():
    provider = KabuStationBrokerAvailabilityProvider(
        snapshot_provider=lambda: _broker_snapshot(
            generated_at=NOW + timedelta(seconds=6)
        ),
        maximum_future_skew_seconds=5, now_provider=lambda: NOW,
    )
    assert provider() is False


def test_broker_provider_exception_is_fail_closed():
    def fail():
        raise RuntimeError("read failed")
    provider = KabuStationBrokerAvailabilityProvider(
        snapshot_provider=fail, now_provider=lambda: NOW
    )
    assert provider() is False
