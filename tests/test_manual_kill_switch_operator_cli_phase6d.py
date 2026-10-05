"""Phase 6-D Step 4D manual Kill Switch operator CLI tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import app.run_manual_kill_switch as cli
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED


def _payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_status_missing_state_fails_closed_without_creating_file(tmp_path, capsys):
    path = tmp_path / "manual.json"

    assert cli.main(["--state-path", str(path), "status"]) == 0

    output = capsys.readouterr().out
    assert "manual_kill_switch=BLOCKED" in output
    assert "manual_blocked=true" in output
    assert "manual_kill_switch_state_unavailable" in output
    assert not path.exists()


def test_engage_persists_blocked_state(tmp_path, capsys):
    path = tmp_path / "manual.json"

    assert cli.main(
        [
            "--state-path",
            str(path),
            "engage",
            "--reason",
            "operator emergency stop",
        ]
    ) == 0

    payload = _payload(path)
    assert payload["manual_blocked"] is True
    assert payload["reason"] == "operator emergency stop"
    assert "manual_kill_switch=BLOCKED" in capsys.readouterr().out


def test_release_requires_exact_confirmation_and_does_not_write_on_failure(
    tmp_path,
):
    path = tmp_path / "manual.json"

    cli.main(
        [
            "--state-path",
            str(path),
            "engage",
            "--reason",
            "initial stop",
        ]
    )
    before = path.read_bytes()

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "--state-path",
                str(path),
                "release",
                "--reason",
                "verified safe",
                "--confirm",
                "release",
            ]
        )

    assert exc_info.value.code == 2
    assert path.read_bytes() == before
    assert _payload(path)["manual_blocked"] is True


def test_release_without_confirmation_is_rejected_without_write(tmp_path):
    path = tmp_path / "manual.json"

    cli.main(
        [
            "--state-path",
            str(path),
            "engage",
            "--reason",
            "initial stop",
        ]
    )
    before = path.read_bytes()

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "--state-path",
                str(path),
                "release",
                "--reason",
                "verified safe",
            ]
        )

    assert exc_info.value.code == 2
    assert path.read_bytes() == before


def test_release_with_exact_confirmation_persists_released_state(
    tmp_path,
    capsys,
):
    path = tmp_path / "manual.json"

    assert cli.main(
        [
            "--state-path",
            str(path),
            "release",
            "--reason",
            "operator verified safe state",
            "--confirm",
            "RELEASE",
        ]
    ) == 0

    payload = _payload(path)
    assert payload["manual_blocked"] is False
    assert payload["reason"] == "operator verified safe state"
    assert "manual_kill_switch=RELEASED" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["engage", "release"])
def test_blank_reason_is_rejected_without_write(tmp_path, command):
    path = tmp_path / "manual.json"
    argv = [
        "--state-path",
        str(path),
        command,
        "--reason",
        "   ",
    ]
    if command == "release":
        argv += ["--confirm", "RELEASE"]

    with pytest.raises(SystemExit) as exc_info:
        cli.main(argv)

    assert exc_info.value.code == 2
    assert not path.exists()


def test_cli_source_has_no_broker_or_network_entrypoints():
    source = inspect.getsource(cli)

    forbidden = (
        "KabuStationClient",
        "KabuStationReadOnlyService",
        "issue_token(",
        "sendorder",
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
    )
    for token in forbidden:
        assert token not in source


def test_step4d_does_not_enable_live_runtime_hard_locks():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False


def test_locked_live_order_adapter_default_remains_unarmed():
    signature = inspect.signature(LockedLiveOrderAdapter)
    assert signature.parameters["runtime_armed"].default is False
