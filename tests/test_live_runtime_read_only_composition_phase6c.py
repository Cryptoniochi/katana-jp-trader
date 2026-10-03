"""Phase 6-C Step 4F-2 read-only provider composition tests."""

import json
from datetime import datetime, timedelta, timezone

from app.live.live_runtime_read_only_composition import (
    LiveRuntimeReadOnlyProviderFactory,
)


NOW = datetime(2026, 10, 3, 0, 30, tzinfo=timezone.utc)


class RecordingDailyTradeRepository:
    def __init__(self):
        self.calls = 0

    def list_closed_trades(self, report_date):
        self.calls += 1
        return ()


class FakeSessionSnapshot:
    is_running = True
    started_at = NOW - timedelta(minutes=10)
    last_heartbeat_at = NOW - timedelta(seconds=10)
    last_cycle_at = NOW - timedelta(seconds=10)


class RecordingSessionService:
    def __init__(self):
        self.snapshot_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return FakeSessionSnapshot()


class RecordingMonitor:
    def __init__(self):
        self.calls = 0

    def evaluate(self, snapshot):
        self.calls += 1
        from app.runtime.runtime_health_monitor_models import (
            RuntimeHealthMonitorReport,
            RuntimeHealthStatus,
        )
        return RuntimeHealthMonitorReport(
            status=RuntimeHealthStatus.HEALTHY,
            checked_at=snapshot.checked_at,
            running=True,
            heartbeat_age_seconds=10.0,
            cycle_age_seconds=10.0,
            reasons=(),
        )


def _write_broker_report(path, *, generated_at=NOW, state="complete"):
    path.write_text(
        json.dumps(
            {
                "generated_at": generated_at.isoformat(),
                "state": state,
                "connected": True,
                "token_issued": True,
                "cash_wallet": None,
                "margin_wallet": None,
                "positions": [],
                "orders": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


def _create(tmp_path, *, report_exists=True):
    repository = RecordingDailyTradeRepository()
    session = RecordingSessionService()
    monitor = RecordingMonitor()
    report_path = tmp_path / "kabu_station_read_only.json"
    if report_exists:
        _write_broker_report(report_path)

    providers = LiveRuntimeReadOnlyProviderFactory.create(
        daily_trade_repository=repository,
        runtime_session_service=session,
        kabu_station_report_path=report_path,
        runtime_health_monitor=monitor,
        now_provider=lambda: NOW,
    )
    return providers, repository, session, monitor, report_path


def test_construction_does_not_evaluate_any_source(tmp_path):
    providers, repository, session, monitor, _ = _create(tmp_path)

    assert providers is not None
    assert repository.calls == 0
    assert session.snapshot_calls == 0
    assert monitor.calls == 0


def test_daily_profit_loss_provider_is_lazy(tmp_path):
    providers, repository, _, _, _ = _create(tmp_path)

    assert providers.daily_profit_loss_provider() == 0.0
    assert repository.calls == 1


def test_consecutive_loss_provider_is_lazy(tmp_path):
    providers, repository, _, _, _ = _create(tmp_path)

    assert providers.consecutive_loss_count_provider() == 0
    assert repository.calls == 1


def test_runtime_health_uses_existing_session_snapshot(tmp_path):
    providers, _, session, monitor, _ = _create(tmp_path)

    assert providers.runtime_health_ok_provider() is True
    assert session.snapshot_calls == 1
    assert monitor.calls == 1


def test_heartbeat_reads_existing_session_without_mutation(tmp_path):
    providers, _, session, _, _ = _create(tmp_path)

    assert providers.heartbeat_alive_provider() is True
    assert session.snapshot_calls == 1


def test_saved_complete_broker_report_is_available(tmp_path):
    providers, _, _, _, _ = _create(tmp_path)

    assert providers.broker_available_provider() is True


def test_missing_broker_report_fails_closed(tmp_path):
    providers, _, _, _, _ = _create(tmp_path, report_exists=False)

    assert providers.broker_available_provider() is False


def test_stale_broker_report_fails_closed(tmp_path):
    providers, _, _, _, report_path = _create(tmp_path)
    _write_broker_report(
        report_path,
        generated_at=NOW - timedelta(seconds=121),
    )

    assert providers.broker_available_provider() is False


def test_partial_broker_report_fails_closed(tmp_path):
    providers, _, _, _, report_path = _create(tmp_path)
    _write_broker_report(report_path, state="partial")

    assert providers.broker_available_provider() is False


def test_corrupt_broker_report_fails_closed(tmp_path):
    providers, _, _, _, report_path = _create(tmp_path)
    report_path.write_text("{not-json", encoding="utf-8")

    assert providers.broker_available_provider() is False


def test_future_broker_report_fails_closed(tmp_path):
    providers, _, _, _, report_path = _create(tmp_path)
    _write_broker_report(
        report_path,
        generated_at=NOW + timedelta(seconds=6),
    )

    assert providers.broker_available_provider() is False
