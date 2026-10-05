"""Phase 6-D production reconciliation and fault-tolerance wiring tests."""

from __future__ import annotations

import inspect

from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionSettings,
)


def test_production_settings_expose_three_way_reconciliation_report_path():
    settings_fields = PaperTradingProductionSettings.__dataclass_fields__

    assert "three_way_reconciliation_report_path" in settings_fields


def test_production_composition_connects_reconciliation_report_provider():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "three_way_reconciliation_report_path=(" in source
    assert "settings.three_way_reconciliation_report_path" in source
    assert ".reconciliation_report_provider" in source


def test_reconciliation_is_not_fabricated_in_production_composition():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "reconciliation_report_provider=lambda: None" not in source


def test_fault_tolerance_is_connected_to_read_only_saved_state_provider():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "fault_tolerance_attempt_provider=lambda: None" not in source
    assert "live_runtime_read_only_providers" in source
    assert ".fault_tolerance_attempt_provider" in source
