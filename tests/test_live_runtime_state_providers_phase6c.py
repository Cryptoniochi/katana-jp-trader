from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.live.live_runtime_state_providers import (
    LatestFaultToleranceAttemptProvider,
    RuntimeHeartbeatSnapshotProvider,
    ThreeWayReconciliationReportReader,
)
from app.live.three_way_reconciliation import (
    OrderMismatch,
    ReconciliationOrder,
    ThreeWayReconciliationReport,
    ThreeWayReconciliationReportWriter,
)
from app.runtime.runtime_heartbeat_service import RuntimeHeartbeatService


NOW = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)


def _report() -> ThreeWayReconciliationReport:
    paper = ReconciliationOrder("o1", "s1", "7203", "buy", 100)
    shadow = ReconciliationOrder("o1", "s1", "7203", "buy", 200)
    return ThreeWayReconciliationReport(
        generated_at=NOW,
        trading_date=NOW.date(),
        state="blocked",
        consistent=False,
        paper_order_count=1,
        shadow_order_count=1,
        matched_order_count=0,
        paper_only_order_ids=(),
        shadow_only_order_ids=(),
        mismatches=(OrderMismatch("o1", paper, shadow),),
        broker_snapshot_connected=True,
        broker_active_order_count=0,
        broker_position_count=0,
        broker_active_order_ids=(),
        broker_position_codes=(),
        live_order_ready=False,
        message="blocked",
    )


def test_three_way_reader_returns_none_when_report_missing(tmp_path):
    assert ThreeWayReconciliationReportReader(tmp_path / "missing.json").read() is None


def test_three_way_reader_round_trips_writer_payload(tmp_path):
    path = tmp_path / "three_way.json"
    original = _report()
    ThreeWayReconciliationReportWriter(path).write(original)

    restored = ThreeWayReconciliationReportReader(path).read()

    assert restored == original


def test_three_way_reader_rejects_naive_generated_at(tmp_path):
    path = tmp_path / "three_way.json"
    payload = _report().to_payload()
    payload["generated_at"] = "2026-10-03T00:00:00"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="timezone-aware"):
        ThreeWayReconciliationReportReader(path).read()


def test_three_way_reader_rejects_malformed_payload(tmp_path):
    path = tmp_path / "three_way.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        ThreeWayReconciliationReportReader(path).read()


def test_latest_fault_tolerance_provider_returns_none_for_empty_history():
    class Source:
        def history(self):
            return ()

    assert LatestFaultToleranceAttemptProvider(Source())() is None


def test_latest_fault_tolerance_provider_returns_last_recorded_attempt():
    first = object()
    second = object()

    class Source:
        def history(self):
            return (first, second)

    provider = LatestFaultToleranceAttemptProvider(Source())
    assert provider() is second


def test_latest_fault_tolerance_provider_does_not_run_fault_tolerance():
    class Source:
        def history(self):
            return ()

        def run_once(self):
            raise AssertionError("provider must never run fault tolerance")

    assert LatestFaultToleranceAttemptProvider(Source())() is None


def test_heartbeat_provider_does_not_record_new_heartbeat():
    service = RuntimeHeartbeatService(
        stale_after=timedelta(minutes=2),
        now_provider=lambda: NOW,
    )
    service.beat(recorded_at=NOW)
    next_sequence = service.next_sequence

    snapshot = RuntimeHeartbeatSnapshotProvider(
        service,
        now_provider=lambda: NOW + timedelta(seconds=30),
    )()

    assert snapshot.is_alive
    assert service.next_sequence == next_sequence


def test_heartbeat_provider_exposes_stale_state_from_real_service():
    service = RuntimeHeartbeatService(
        stale_after=timedelta(minutes=2),
        now_provider=lambda: NOW,
    )
    service.beat(recorded_at=NOW)

    snapshot = RuntimeHeartbeatSnapshotProvider(
        service,
        now_provider=lambda: NOW + timedelta(minutes=3),
    )()

    assert not snapshot.is_alive


def test_heartbeat_provider_exposes_missing_state_fail_closed():
    service = RuntimeHeartbeatService(
        stale_after=timedelta(minutes=2),
        now_provider=lambda: NOW,
    )

    snapshot = RuntimeHeartbeatSnapshotProvider(
        service,
        now_provider=lambda: NOW,
    )()

    assert not snapshot.is_alive
