from datetime import datetime, timezone
from io import StringIO

import pytest

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveTradingLockError,
    LiveTradingUnavailableError,
    TradingExecutionMode,
)
from app.run_market_session import _run_selected_runtime


NOW = datetime(2026, 10, 14, 0, 15, tzinfo=timezone.utc)


def _call(settings, runner):
    return _run_selected_runtime(
        settings=settings,
        application_arguments=["--check"],
        environ={},
        output=StringIO(),
        error_output=StringIO(),
        now_provider=lambda: NOW,
        paper_trading_runner=runner,
    )


def test_paper_keeps_existing_runner():
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return 17

    result = _call(
        ExecutionModeSettings(mode=TradingExecutionMode.PAPER),
        runner,
    )

    assert result == 17
    assert len(calls) == 1


def test_shadow_keeps_existing_runner_and_never_enters_live_boundary():
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return 23

    result = _call(
        ExecutionModeSettings(mode=TradingExecutionMode.SHADOW),
        runner,
    )

    assert result == 23
    assert len(calls) == 1


def test_live_without_daily_arming_never_falls_back_to_paper():
    calls = []

    with pytest.raises(LiveTradingLockError):
        _call(
            ExecutionModeSettings(mode=TradingExecutionMode.LIVE),
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_armed_live_still_fails_closed_until_dedicated_runner_is_wired():
    calls = []
    settings = ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-10-14",
    )

    with pytest.raises(
        LiveTradingUnavailableError,
        match="Refusing to fall back to Paper Trading",
    ):
        _call(
            settings,
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []
