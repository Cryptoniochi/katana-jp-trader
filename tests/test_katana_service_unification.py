"""Sprint99-3 Service Manager統合テスト。"""

from pathlib import Path

from app.runtime.katana_service_manager import (
    build_dashboard_command,
)


def test_dashboard_command_starts_dashboard_directly() -> None:
    command = build_dashboard_command(
        database_path=Path("data/katana.db"),
        host="100.64.14.23",
        port=8000,
        service_status_path=Path(
            "reports/service/katana_service_status.json"
        ),
    )

    assert "app.dashboard" in command
    assert "app.run_dashboard_resident" not in command
    assert "--service-status" in command
    assert "100.64.14.23" in command
