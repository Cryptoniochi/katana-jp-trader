"""Guardrails for the dedicated Phase 2 Live account-state composition."""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

from app.live.live_account_runtime_composition import (
    LiveAccountRuntimeProviderFactory,
)


class _NoNetworkClient:
    def __getattr__(self, name):
        raise AssertionError(f"construction accessed broker client: {name}")


class _Repository:
    def list_closed_trades(self, report_date):
        return ()


def test_live_account_composition_is_separate_from_paper_runtime():
    source = inspect.getsource(LiveAccountRuntimeProviderFactory.create)
    assert "KabuStationReadOnlyService(" in source
    assert "KabuStationLiveAccountStateService(" in source
    assert "KabuStationLiveRiskPortfolioProvider(" in source
    assert "KabuStationLivePositionProvider(" in source
    assert "PaperBroker" not in source


def test_live_account_composition_construction_performs_no_network_access(tmp_path):
    bundle = LiveAccountRuntimeProviderFactory.create(
        kabu_client=_NoNetworkClient(),
        daily_trade_repository=_Repository(),
        kabu_station_report_path=tmp_path / "broker.json",
        live_equity_peak_path=tmp_path / "peak.json",
        now_provider=lambda: datetime(2026, 10, 13, tzinfo=timezone.utc),
    )
    assert bundle.account_state_service is not None
    assert bundle.risk_portfolio_provider is not None
    assert bundle.position_provider is not None


def test_paper_composition_does_not_import_new_live_account_composition():
    source = Path("app/runtime/paper_trading_composition.py").read_text(
        encoding="utf-8"
    )
    assert "LiveAccountRuntimeProviderFactory" not in source
    assert "KabuStationLiveAccountStateService" not in source


def test_legacy_live_read_only_composition_remains_saved_state_only():
    source = Path("app/live/live_runtime_read_only_composition.py").read_text(
        encoding="utf-8"
    )
    assert "KabuStationReadOnlyService(" not in source
    assert "KabuStationReadOnlyReportReader(" in source
    assert "KabuStationRiskPortfolioProvider(" in source
