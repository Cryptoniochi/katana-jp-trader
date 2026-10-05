"""Phase 6-D Step 4B manual Kill Switch read-only provider wiring tests."""

from __future__ import annotations

import inspect
from pathlib import Path

from app.live.live_runtime_read_only_composition import (
    LiveRuntimeReadOnlyProviderFactory,
)


def test_factory_exposes_manual_kill_switch_state_path():
    signature = inspect.signature(LiveRuntimeReadOnlyProviderFactory.create)

    assert "manual_kill_switch_state_path" in signature.parameters


def test_factory_connects_manual_kill_switch_reader():
    source = inspect.getsource(LiveRuntimeReadOnlyProviderFactory.create)

    assert "ManualKillSwitchStateReader" in source
    assert ".manual_blocked" in source


def test_unconfigured_manual_provider_fails_closed():
    source = inspect.getsource(LiveRuntimeReadOnlyProviderFactory.create)

    assert "def manual_blocked_provider() -> bool:" in source
    assert "return True" in source
    assert "return False" not in source


def test_factory_contains_no_manual_kill_switch_writer():
    module_source = inspect.getsource(
        __import__(
            "app.live.live_runtime_read_only_composition",
            fromlist=["dummy"],
        )
    )

    assert "ManualKillSwitchStateWriter" not in module_source
    assert ".engage(" not in module_source
    assert ".release(" not in module_source


def test_factory_contains_no_network_or_order_submission():
    source = inspect.getsource(LiveRuntimeReadOnlyProviderFactory.create)

    forbidden = (
        "sendorder",
        "submit_order",
        "issue_token",
        ".collect()",
        "LockedLiveBrokerTransport",
    )
    for pattern in forbidden:
        assert pattern not in source


def test_manual_reader_is_fail_closed_for_missing_file(tmp_path):
    from app.live.live_manual_kill_switch_state_reader import (
        ManualKillSwitchStateReader,
    )

    provider = ManualKillSwitchStateReader(
        Path(tmp_path) / "missing.json"
    ).manual_blocked

    assert provider() is True
