"""Dashboard resident launcherのテスト。"""

from pathlib import Path

import app.run_dashboard_resident as module


def test_build_dashboard_command_uses_host() -> None:
    settings = module.DashboardResidentSettings(
        database_path=Path("data/katana.db"),
        port=8000,
        host_mode="tailscale",
    )

    command = module.build_dashboard_command(
        settings=settings,
        host="100.64.14.23",
    )

    assert "--host" in command
    assert "100.64.14.23" in command
    assert "--no-browser" in command


def test_local_mode_dry_run(
    capsys,
) -> None:
    result = module.run(
        [
            "--host-mode",
            "local",
            "--dry-run",
        ]
    )

    assert result == 0
    assert "127.0.0.1" in capsys.readouterr().out
