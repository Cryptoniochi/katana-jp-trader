"""Live Runtime Kill Switch状態Providerのテスト。"""

from datetime import datetime, timezone

import pytest

from app.live.live_runtime_kill_switch_state import (
    LiveRuntimeKillSwitchStateProvider,
)
from app.risk.kill_switch_service import KillSwitchService


NOW = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)


def _healthy_provider(**overrides):
    values = {
        "manual_blocked_provider": lambda: False,
        "daily_profit_loss_provider": lambda: 0.0,
        "consecutive_loss_count_provider": lambda: 0,
        "runtime_health_ok_provider": lambda: True,
        "heartbeat_alive_provider": lambda: True,
        "broker_available_provider": lambda: True,
        "now_provider": lambda: NOW,
    }
    values.update(overrides)
    return LiveRuntimeKillSwitchStateProvider(**values)


def test_all_real_inputs_healthy_allows_new_entries():
    evaluation = KillSwitchService().evaluate(_healthy_provider()())
    assert evaluation.allows_new_entries is True
    assert evaluation.is_blocked is False


@pytest.mark.parametrize(
    "missing_name",
    [
        "manual_blocked_provider",
        "daily_profit_loss_provider",
        "consecutive_loss_count_provider",
        "runtime_health_ok_provider",
        "heartbeat_alive_provider",
        "broker_available_provider",
    ],
)
def test_missing_input_fails_closed(missing_name):
    provider = _healthy_provider(**{missing_name: None})
    assert KillSwitchService().evaluate(provider()).is_blocked is True


@pytest.mark.parametrize(
    "provider_name",
    [
        "manual_blocked_provider",
        "daily_profit_loss_provider",
        "consecutive_loss_count_provider",
        "runtime_health_ok_provider",
        "heartbeat_alive_provider",
        "broker_available_provider",
    ],
)
def test_provider_exception_fails_closed(provider_name):
    def fail():
        raise RuntimeError("state unavailable")
    provider = _healthy_provider(**{provider_name: fail})
    assert KillSwitchService().evaluate(provider()).is_blocked is True


def test_daily_loss_at_limit_blocks():
    snapshot = _healthy_provider(
        daily_profit_loss_provider=lambda: -50_000.0
    )()
    assert snapshot.daily_loss_blocked is True


def test_daily_loss_above_limit_does_not_block():
    snapshot = _healthy_provider(
        daily_profit_loss_provider=lambda: -49_999.0
    )()
    assert snapshot.daily_loss_blocked is False


def test_non_finite_daily_profit_loss_fails_closed():
    snapshot = _healthy_provider(
        daily_profit_loss_provider=lambda: float("nan")
    )()
    assert snapshot.daily_loss_blocked is True


def test_consecutive_loss_at_limit_blocks():
    snapshot = _healthy_provider(
        consecutive_loss_count_provider=lambda: 3
    )()
    assert snapshot.consecutive_loss_blocked is True


def test_negative_consecutive_loss_fails_closed():
    snapshot = _healthy_provider(
        consecutive_loss_count_provider=lambda: -1
    )()
    assert snapshot.consecutive_loss_blocked is True


def test_manual_block_blocks():
    provider = _healthy_provider(manual_blocked_provider=lambda: True)
    assert KillSwitchService().evaluate(provider()).is_blocked is True


def test_runtime_health_false_blocks():
    provider = _healthy_provider(runtime_health_ok_provider=lambda: False)
    assert KillSwitchService().evaluate(provider()).is_blocked is True


def test_heartbeat_false_blocks():
    provider = _healthy_provider(heartbeat_alive_provider=lambda: False)
    assert KillSwitchService().evaluate(provider()).is_blocked is True


def test_broker_unavailable_blocks():
    provider = _healthy_provider(broker_available_provider=lambda: False)
    assert KillSwitchService().evaluate(provider()).is_blocked is True


def test_naive_now_is_rejected():
    provider = _healthy_provider(
        now_provider=lambda: datetime(2026, 10, 3, 0, 0)
    )
    with pytest.raises(ValueError):
        provider()


def test_boolean_consecutive_loss_is_invalid_and_blocks():
    snapshot = _healthy_provider(
        consecutive_loss_count_provider=lambda: False
    )()
    assert snapshot.consecutive_loss_blocked is True
