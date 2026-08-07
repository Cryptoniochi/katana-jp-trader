"""既存Dashboard採用機能のテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.runtime.katana_service_manager import (
    KatanaServiceManager,
    ManagedProcessDefinition,
)
from app.runtime.katana_service_models import (
    ManagedComponentName,
    ManagedComponentState,
)


NOW = datetime(
    2026,
    8,
    6,
    tzinfo=timezone.utc,
)


class NeverPopen:
    def __call__(self, *_args, **_kwargs):
        raise AssertionError(
            "既存Dashboardが正常なら起動してはいけません。"
        )


def test_existing_dashboard_is_adopted(
    tmp_path: Path,
) -> None:
    manager = KatanaServiceManager(
        definitions=(
            ManagedProcessDefinition(
                name=ManagedComponentName.DASHBOARD,
                command=("python", "-m", "app.dashboard"),
                enabled=True,
                external_health_check=lambda: True,
            ),
        ),
        status_path=tmp_path / "status.json",
        now_provider=lambda: NOW,
        popen_factory=NeverPopen(),
        readiness_probe=None,
    )

    manager.start_enabled_components()
    status = manager.create_status()
    component = status.components[0]

    assert component.state is ManagedComponentState.RUNNING
    assert component.process_id is None
    assert "adopted" in (component.message or "").lower()
    assert status.service_state == "healthy"
