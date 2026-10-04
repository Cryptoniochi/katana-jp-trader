"""Phase 6-D Step 1D composition tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.live.live_runtime_read_only_composition import (
    LiveRuntimeReadOnlyProviderFactory,
)


NOW = datetime(2026, 10, 4, 12, 30, tzinfo=timezone.utc)


class DailyRepo:
    def list_closed_trades(self, report_date):
        return ()


class Session:
    def snapshot(self):
        raise RuntimeError("must not be evaluated during construction")


def test_factory_construction_does_not_read_or_create_state(tmp_path):
    broker_report = tmp_path / "broker.json"
    peak_state = tmp_path / "peak.json"

    providers = LiveRuntimeReadOnlyProviderFactory.create(
        daily_trade_repository=DailyRepo(),
        runtime_session_service=Session(),
        kabu_station_report_path=broker_report,
        live_equity_peak_path=peak_state,
        now_provider=lambda: NOW,
    )

    assert providers.portfolio_provider is not None
    assert providers.saved_broker_snapshot_provider is not None
    assert not broker_report.exists()
    assert not peak_state.exists()


def test_missing_peak_state_makes_portfolio_fail_closed(tmp_path):
    broker_report = tmp_path / "broker.json"
    broker_report.write_text(
        """{
  "generated_at": "2026-10-04T12:30:00+00:00",
  "state": "complete",
  "connected": true,
  "token_issued": true,
  "cash_wallet": {"StockAccountWallet": 1000000},
  "margin_wallet": {},
  "positions": [],
  "orders": [],
  "errors": []
}
""",
        encoding="utf-8",
    )

    providers = LiveRuntimeReadOnlyProviderFactory.create(
        daily_trade_repository=DailyRepo(),
        runtime_session_service=Session(),
        kabu_station_report_path=broker_report,
        live_equity_peak_path=tmp_path / "missing_peak.json",
        now_provider=lambda: NOW,
    )

    with pytest.raises(RuntimeError):
        providers.portfolio_provider()


def test_factory_has_no_live_execution_or_network_method():
    forbidden = {
        "collect",
        "issue_token",
        "send",
        "sendorder",
        "submit",
        "submit_order",
        "cancel_order",
    }
    assert forbidden.isdisjoint(dir(LiveRuntimeReadOnlyProviderFactory))


def test_factory_keeps_phase6c_call_signature_compatible(tmp_path):
    """Existing callers may omit the new peak path."""
    providers = LiveRuntimeReadOnlyProviderFactory.create(
        daily_trade_repository=DailyRepo(),
        runtime_session_service=Session(),
        kabu_station_report_path=tmp_path / "broker.json",
        now_provider=lambda: NOW,
    )

    assert providers.portfolio_provider is not None
    assert not (tmp_path / "live_equity_peak.json").exists()
