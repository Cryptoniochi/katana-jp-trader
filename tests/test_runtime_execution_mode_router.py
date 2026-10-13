from datetime import date

import pytest

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveTradingLockError,
    RuntimeExecutionModeRouter,
    TradingExecutionMode,
)

DAY=date(2026,10,13)

def router():
    return RuntimeExecutionModeRouter(
        paper_runtime=object(),
        shadow_runtime=object(),
        live_runtime=object(),
    )

def test_runtime_router_preserves_paper_path():
    r=router()
    selected=r.resolve(
        ExecutionModeSettings(mode=TradingExecutionMode.PAPER),
        trading_date=DAY,
    )
    assert selected is r.paper_runtime

def test_runtime_router_preserves_shadow_path():
    r=router()
    selected=r.resolve(
        ExecutionModeSettings(mode=TradingExecutionMode.SHADOW),
        trading_date=DAY,
    )
    assert selected is r.shadow_runtime

def test_runtime_router_blocks_unarmed_live():
    r=router()
    with pytest.raises(LiveTradingLockError):
        r.resolve(
            ExecutionModeSettings(mode=TradingExecutionMode.LIVE),
            trading_date=DAY,
        )

def test_runtime_router_selects_distinct_live_runtime_only_when_daily_armed():
    r=router()
    selected=r.resolve(
        ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation="KATANA-LIVE-2026-10-13",
        ),
        trading_date=DAY,
    )
    assert selected is r.live_runtime
    assert selected is not r.paper_runtime
    assert selected is not r.shadow_runtime
