"""Phase 6-E Step 5 production E2E activation safety tests."""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_activation_e2e_composition import (
    ProductionLiveActivationE2EFactory,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


DAY = date(2026, 10, 7)
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


class ReadinessGateStub:
    def __init__(self, *, ready=True):
        self.ready = ready
        self.calls = 0
        self.settings = None
        self.day = None

    def check(self, *, execution_settings, trading_date):
        self.calls += 1
        self.settings = execution_settings
        self.day = trading_date
        return SimpleNamespace(activation_ready=self.ready)


class Providers:
    def __init__(self, *, manual=False, reconciliation=True):
        self.runtime_health_ok_provider = lambda: True
        self.heartbeat_alive_provider = lambda: True
        self.broker_available_provider = lambda: True
        self.manual_blocked_provider = lambda: manual
        self.reconciliation_report_provider = (
            lambda: SimpleNamespace(consistent=reconciliation)
        )


def settings():
    return ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-10-07",
    )


def bundle(gate):
    return SimpleNamespace(final_live_readiness_gate=gate)


def test_factory_construction_is_inert():
    gate = ReadinessGateStub()
    e2e = ProductionLiveActivationE2EFactory.create(
        production_bundle=bundle(gate),
        read_only_providers=Providers(),
        execution_settings=settings(),
        trading_date=DAY,
    )
    assert gate.calls == 0
    assert e2e is not None


def test_e2e_ready_path_calls_final_readiness_once_and_authorizes():
    gate = ReadinessGateStub(ready=True)
    e2e = ProductionLiveActivationE2EFactory.create(
        production_bundle=bundle(gate),
        read_only_providers=Providers(),
        execution_settings=settings(),
        trading_date=DAY,
    )
    report = e2e.evaluate()
    assert gate.calls == 1
    assert gate.settings == settings()
    assert gate.day == DAY
    assert report.authorization_ready is True


def test_final_readiness_false_fails_closed():
    gate = ReadinessGateStub(ready=False)
    e2e = ProductionLiveActivationE2EFactory.create(
        production_bundle=bundle(gate),
        read_only_providers=Providers(),
        execution_settings=settings(),
        trading_date=DAY,
    )
    assert e2e.evaluate().authorization_ready is False
    assert gate.calls == 1


def test_manual_block_after_final_readiness_still_fails_closed():
    gate = ReadinessGateStub(ready=True)
    e2e = ProductionLiveActivationE2EFactory.create(
        production_bundle=bundle(gate),
        read_only_providers=Providers(manual=True),
        execution_settings=settings(),
        trading_date=DAY,
    )
    assert e2e.evaluate().authorization_ready is False


def test_reconciliation_block_after_final_readiness_still_fails_closed():
    gate = ReadinessGateStub(ready=True)
    e2e = ProductionLiveActivationE2EFactory.create(
        production_bundle=bundle(gate),
        read_only_providers=Providers(reconciliation=False),
        execution_settings=settings(),
        trading_date=DAY,
    )
    assert e2e.evaluate().authorization_ready is False


def test_missing_final_readiness_gate_is_rejected_at_composition():
    with pytest.raises(ValueError, match="Final Live Readiness"):
        ProductionLiveActivationE2EFactory.create(
            production_bundle=bundle(None),
            read_only_providers=Providers(),
            execution_settings=settings(),
            trading_date=DAY,
        )


def test_all_hard_locks_remain_closed_before_and_after_e2e_review():
    before = (
        LIVE_ORDER_TRANSMISSION_ENABLED,
        LIVE_BROKER_TRANSPORT_ENABLED,
        LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    )
    e2e = ProductionLiveActivationE2EFactory.create(
        production_bundle=bundle(ReadinessGateStub()),
        read_only_providers=Providers(),
        execution_settings=settings(),
        trading_date=DAY,
    )
    e2e.evaluate()
    after = (
        LIVE_ORDER_TRANSMISSION_ENABLED,
        LIVE_BROKER_TRANSPORT_ENABLED,
        LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    )
    assert before == (False, False, False)
    assert after == (False, False, False)


def test_e2e_composition_exposes_no_runtime_start_recovery_or_order_path():
    source = inspect.getsource(ProductionLiveActivationE2EFactory).lower()
    forbidden = (
        ".run()",
        ".start(",
        ".recover(",
        ".release(",
        "sendorder",
        "send_order(",
        "submit_order(",
        "runtime_armed",
        "kabustationclient",
        "kabustationreadservice",
        "requests.",
        "httpx.",
        "urllib.",
    )
    assert all(token not in source for token in forbidden)


def test_production_bundle_contract_is_read_only_field_only():
    source = inspect.getsource(
        __import__(
            "app.live.live_activation_e2e_composition",
            fromlist=["ProductionLiveActivationBundleLike"],
        ).ProductionLiveActivationBundleLike
    )
    assert "final_live_readiness_gate" in source
    assert "run" not in source
    assert "start" not in source
