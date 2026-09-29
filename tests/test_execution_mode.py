"""安全な実行モード選択とLive二重解除のテスト。"""

from datetime import date

import pytest

from app.live.execution_mode import (
    ExecutionModeRouter,
    ExecutionModeSettings,
    LiveArmingPolicy,
    LiveTradingLockError,
    LiveTradingUnavailableError,
    TradingExecutionMode,
)


TRADING_DATE = date(2026, 9, 30)


class FakeBroker:
    """モード選択確認だけに使うBroker。"""


def test_environment_defaults_to_paper() -> None:
    settings = ExecutionModeSettings.from_environment({})

    assert settings.mode is TradingExecutionMode.PAPER
    assert settings.live_armed is False
    assert settings.live_confirmation is None


def test_environment_accepts_shadow() -> None:
    settings = ExecutionModeSettings.from_environment(
        {"KATANA_EXECUTION_MODE": " SHADOW "}
    )

    assert settings.mode is TradingExecutionMode.SHADOW


def test_environment_rejects_unknown_mode() -> None:
    with pytest.raises(
        ValueError,
        match="paper、shadow、live",
    ):
        ExecutionModeSettings.from_environment(
            {"KATANA_EXECUTION_MODE": "production"}
        )


def test_live_requires_armed_switch() -> None:
    policy = LiveArmingPolicy()
    settings = ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=False,
        live_confirmation="KATANA-LIVE-2026-09-30",
    )

    with pytest.raises(
        LiveTradingLockError,
        match="ARMED=YES",
    ):
        policy.require_authorized(
            settings,
            trading_date=TRADING_DATE,
        )


def test_live_requires_same_day_confirmation() -> None:
    policy = LiveArmingPolicy()
    settings = ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-09-29",
    )

    with pytest.raises(
        LiveTradingLockError,
        match="当日のLive確認文字列",
    ):
        policy.require_authorized(
            settings,
            trading_date=TRADING_DATE,
        )


def test_live_policy_accepts_both_daily_unlocks() -> None:
    policy = LiveArmingPolicy()
    settings = ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation=(
            policy.expected_confirmation(TRADING_DATE)
        ),
    )

    policy.require_authorized(
        settings,
        trading_date=TRADING_DATE,
    )


def test_router_selects_paper_and_shadow() -> None:
    paper = FakeBroker()
    shadow = FakeBroker()
    router = ExecutionModeRouter(
        paper_broker=paper,
        shadow_broker=shadow,
    )

    assert router.resolve(
        ExecutionModeSettings(),
        trading_date=TRADING_DATE,
    ) is paper
    assert router.resolve(
        ExecutionModeSettings(
            mode=TradingExecutionMode.SHADOW
        ),
        trading_date=TRADING_DATE,
    ) is shadow


def test_router_refuses_live_even_when_unlocked() -> None:
    router = ExecutionModeRouter(
        paper_broker=FakeBroker(),
        shadow_broker=FakeBroker(),
    )
    settings = ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-09-30",
    )

    with pytest.raises(
        LiveTradingUnavailableError,
        match="未導入",
    ):
        router.resolve(
            settings,
            trading_date=TRADING_DATE,
        )
