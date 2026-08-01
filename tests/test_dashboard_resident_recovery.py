"""Dashboard resident retry/supervisorのテスト。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import app.run_dashboard_resident as module


def test_wait_for_tailscale_retries_until_ready() -> None:
    calls = []
    sleeps = []

    def resolver() -> str:
        calls.append(1)

        if len(calls) < 3:
            raise module.DashboardResidentLaunchError(
                "not ready"
            )

        return "100.64.14.23"

    result = module.wait_for_tailscale_ip(
        attempts=5,
        wait_seconds=2.0,
        resolver=resolver,
        sleep=sleeps.append,
    )

    assert result == "100.64.14.23"
    assert len(calls) == 3
    assert sleeps == [2.0, 2.0]


def test_wait_for_tailscale_times_out() -> None:
    def resolver() -> str:
        raise module.DashboardResidentLaunchError(
            "not ready"
        )

    with pytest.raises(
        module.DashboardResidentLaunchError,
        match="タイムアウト",
    ):
        module.wait_for_tailscale_ip(
            attempts=2,
            wait_seconds=0.0,
            resolver=resolver,
            sleep=lambda _seconds: None,
        )


def test_supervisor_restarts_after_failure() -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=1),
            SimpleNamespace(returncode=0),
        ]
    )
    calls = []
    sleeps = []

    def runner(command, **kwargs):
        calls.append(
            (
                command,
                kwargs,
            )
        )
        return next(responses)

    result = module.run_dashboard_supervisor(
        settings=module.DashboardResidentSettings(
            database_path=Path(
                "data/katana.db"
            ),
            host_mode="local",
            restart_delay_seconds=3.0,
            max_restarts=2,
        ),
        host="127.0.0.1",
        runner=runner,
        sleep=sleeps.append,
    )

    assert result == 0
    assert len(calls) == 2
    assert sleeps == [3.0]


def test_supervisor_stops_at_restart_limit() -> None:
    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=1)

    result = module.run_dashboard_supervisor(
        settings=module.DashboardResidentSettings(
            database_path=Path(
                "data/katana.db"
            ),
            host_mode="local",
            restart_delay_seconds=0.0,
            max_restarts=1,
        ),
        host="127.0.0.1",
        runner=runner,
        sleep=lambda _seconds: None,
    )

    assert result == 1
