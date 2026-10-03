"""Phase 6-C Step 4F-3 paper runtime read-only live-state attachment tests."""

import inspect
from pathlib import Path

from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionSettings,
)
from app.settings import ROOT_DIR


def _settings(**overrides):
    values = {
        "database_path": Path("data/test-katana.db"),
        "codes": ("7203",),
        # Production settings correctly require this value in realtime mode.
        # Tests provide a non-secret placeholder because no kabu Station
        # connection or network call is performed here.
        "kabu_station_api_password": "test-password",
    }
    values.update(overrides)
    return PaperTradingProductionSettings(**values)


def test_live_runtime_hard_lock_remains_disabled():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_saved_broker_report_has_fail_closed_default_path():
    settings = _settings()

    assert settings.live_read_only_report_path == (
        ROOT_DIR / "reports/live/kabu_station_read_only.json"
    ).resolve()


def test_saved_broker_report_accepts_absolute_path(tmp_path):
    path = (tmp_path / "broker.json").resolve()
    settings = _settings(live_read_only_report_path=path)

    assert settings.live_read_only_report_path == path


def test_composition_uses_read_only_provider_factory():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "LiveRuntimeReadOnlyProviderFactory.create" in source
    assert "SQLiteDailyTradeRepository" in source
    assert "runtime_session_service=runtime_session" in source
    assert "settings.live_read_only_report_path" in source


def test_composition_uses_state_connected_disabled_attachment():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "disabled_state_connected_attachment" in source
    assert "disabled_attachment(" not in source


def test_manual_kill_switch_is_not_connected_by_paper_composition():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "manual_blocked_provider" not in source


def test_unavailable_live_portfolio_fails_closed():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "def unavailable_live_portfolio" in source
    assert "Live portfolio state is not connected in Phase 6-C." in source


def test_composition_does_not_create_kabu_read_only_service():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "KabuStationReadOnlyService" not in source
    assert "issue_token()" not in source


def test_paper_max_daily_loss_is_reused_for_live_kill_switch():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "max_daily_loss=settings.max_daily_loss" in source
