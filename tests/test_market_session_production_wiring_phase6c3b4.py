from datetime import datetime, timezone
from io import StringIO

import pytest

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveTradingUnavailableError,
    TradingExecutionMode,
)
from app.run_market_session import _run_selected_runtime


NOW=lambda: datetime(2026,10,14,1,0,tzinfo=timezone.utc)


def cfg(mode, *, armed=False, confirmation=None):
    return ExecutionModeSettings(
        mode=mode,
        live_armed=armed,
        live_confirmation=confirmation,
    )


def invoke(settings, paper, live):
    return _run_selected_runtime(
        settings=settings,
        application_arguments=(),
        environ={},
        output=StringIO(),
        error_output=StringIO(),
        now_provider=NOW,
        paper_trading_runner=paper,
        live_trading_runner=live,
    )


def test_paper_routes_only_to_paper():
    calls=[]
    assert invoke(
        cfg(TradingExecutionMode.PAPER),
        lambda *a,**k: calls.append("paper") or 7,
        lambda *a,**k: calls.append("live") or 9,
    ) == 7
    assert calls == ["paper"]


def test_shadow_preserves_existing_application_runner():
    calls=[]
    assert invoke(
        cfg(TradingExecutionMode.SHADOW),
        lambda *a,**k: calls.append("shadow") or 8,
        lambda *a,**k: calls.append("live") or 9,
    ) == 8
    assert calls == ["shadow"]


def test_live_requires_daily_arming_before_live_callable():
    calls=[]
    with pytest.raises(Exception):
        invoke(
            cfg(TradingExecutionMode.LIVE),
            lambda *a,**k: calls.append("paper") or 7,
            lambda *a,**k: calls.append("live") or 9,
        )
    assert calls == []


def test_authorized_live_routes_only_to_live():
    calls=[]
    result=invoke(
        cfg(
            TradingExecutionMode.LIVE,
            armed=True,
            confirmation="KATANA-LIVE-2026-10-14",
        ),
        lambda *a,**k: calls.append("paper") or 7,
        lambda *a,**k: calls.append("live") or 9,
    )
    assert result == 9
    assert calls == ["live"]
