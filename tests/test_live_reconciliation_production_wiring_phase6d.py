"""Phase 6-D Step 2B production composition wiring tests."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionSettings,
)


def test_settings_define_normalized_three_way_reconciliation_path(tmp_path):
    relative = Path("reports/live/custom_three_way.json")
    settings = PaperTradingProductionSettings(
        database_path=tmp_path / "katana.db",
        codes=("7203",),
        kabu_station_api_password="test-password",
        three_way_reconciliation_report_path=relative,
    )

    assert settings.three_way_reconciliation_report_path.is_absolute()
    assert settings.three_way_reconciliation_report_path.name == (
        "custom_three_way.json"
    )


def test_production_composition_connects_saved_live_portfolio_provider():
    source = inspect.getsource(PaperTradingComposition.create)

    assert (
        "live_runtime_read_only_providers.portfolio_provider"
        in source
    )
    assert "unavailable_live_portfolio" not in source


def test_production_composition_connects_saved_reconciliation_provider():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "three_way_reconciliation_report_path" in source
    assert ".reconciliation_report_provider" in source
    assert "reconciliation_report_provider=lambda: None" not in source


def test_fault_tolerance_remains_fail_closed_and_unconnected():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "fault_tolerance_attempt_provider=lambda: None" in source


def test_step2b_does_not_add_live_execution_unlock_text():
    source = inspect.getsource(PaperTradingComposition.create)

    forbidden = (
        "sendorder",
        "submit_order",
        "LIVE_BROKER_TRANSPORT_ENABLED = True",
        "LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = True",
        "runtime_armed=True",
    )
    for marker in forbidden:
        assert marker not in source
