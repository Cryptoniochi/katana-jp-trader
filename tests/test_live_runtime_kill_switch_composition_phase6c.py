"""Tests for Phase 6-C live-runtime Kill Switch composition."""

from datetime import datetime, timezone

from app.live.live_runtime_kill_switch_composition import (
    LiveRuntimeKillSwitchComposition,
)
from app.risk.kill_switch_models import KillSwitchReason, KillSwitchStatus
from app.risk.kill_switch_service import KillSwitchService


NOW = datetime(2026, 10, 3, 1, 2, 3, tzinfo=timezone.utc)


def _composition(
    *,
    manual=None,
    pnl=0.0,
    losses=0,
    health=True,
    heartbeat=True,
    broker=True,
):
    return LiveRuntimeKillSwitchComposition(
        manual_blocked_provider=manual,
        daily_profit_loss_provider=lambda: pnl,
        consecutive_loss_count_provider=lambda: losses,
        runtime_health_ok_provider=lambda: health,
        heartbeat_alive_provider=lambda: heartbeat,
        broker_available_provider=lambda: broker,
        max_daily_loss=50_000.0,
        max_consecutive_losses=3,
        now_provider=lambda: NOW,
    )


def _evaluation(composition):
    return KillSwitchService().evaluate(composition())


def test_manual_source_missing_is_fail_closed():
    result = _evaluation(_composition())
    assert result.status is KillSwitchStatus.BLOCKED
    assert result.reason is KillSwitchReason.MANUAL


def test_all_connected_healthy_sources_allow_active_snapshot():
    result = _evaluation(_composition(manual=lambda: False))
    assert result.status is KillSwitchStatus.ACTIVE
    assert result.reason is KillSwitchReason.NONE


def test_manual_block_has_highest_priority():
    result = _evaluation(
        _composition(manual=lambda: True, pnl=-100_000.0, health=False)
    )
    assert result.reason is KillSwitchReason.MANUAL


def test_daily_loss_limit_blocks():
    result = _evaluation(
        _composition(manual=lambda: False, pnl=-50_000.0)
    )
    assert result.reason is KillSwitchReason.DAILY_LOSS


def test_consecutive_loss_limit_blocks():
    result = _evaluation(
        _composition(manual=lambda: False, losses=3)
    )
    assert result.reason is KillSwitchReason.CONSECUTIVE_LOSS


def test_runtime_health_blocks():
    result = _evaluation(
        _composition(manual=lambda: False, health=False)
    )
    assert result.reason is KillSwitchReason.RUNTIME_HEALTH


def test_heartbeat_blocks():
    result = _evaluation(
        _composition(manual=lambda: False, heartbeat=False)
    )
    assert result.reason is KillSwitchReason.HEARTBEAT


def test_broker_unavailable_blocks():
    result = _evaluation(
        _composition(manual=lambda: False, broker=False)
    )
    assert result.reason is KillSwitchReason.BROKER


def test_daily_loss_provider_failure_is_fail_closed():
    def fail():
        raise RuntimeError("daily P/L unavailable")

    composition = LiveRuntimeKillSwitchComposition(
        manual_blocked_provider=lambda: False,
        daily_profit_loss_provider=fail,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=lambda: True,
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=lambda: True,
        now_provider=lambda: NOW,
    )
    snapshot = composition()
    assert snapshot.daily_loss_blocked is True


def test_runtime_health_provider_failure_is_fail_closed():
    def fail():
        raise RuntimeError("health unavailable")

    composition = LiveRuntimeKillSwitchComposition(
        manual_blocked_provider=lambda: False,
        daily_profit_loss_provider=lambda: 0.0,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=fail,
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=lambda: True,
        now_provider=lambda: NOW,
    )
    snapshot = composition()
    assert snapshot.runtime_health_ok is False


def test_broker_provider_failure_is_fail_closed():
    def fail():
        raise RuntimeError("broker unavailable")

    composition = LiveRuntimeKillSwitchComposition(
        manual_blocked_provider=lambda: False,
        daily_profit_loss_provider=lambda: 0.0,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=lambda: True,
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=fail,
        now_provider=lambda: NOW,
    )
    snapshot = composition()
    assert snapshot.broker_available is False


def test_providers_are_re_evaluated_for_each_snapshot():
    state = {"health": True}
    composition = LiveRuntimeKillSwitchComposition(
        manual_blocked_provider=lambda: False,
        daily_profit_loss_provider=lambda: 0.0,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=lambda: state["health"],
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=lambda: True,
        now_provider=lambda: NOW,
    )
    assert composition().runtime_health_ok is True
    state["health"] = False
    assert composition().runtime_health_ok is False
