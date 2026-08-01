"""Morning Pre-Flight SchedulerのService統合テスト。"""

from app.runtime.katana_service_manager import (
    build_morning_preflight_scheduler_command,
)


def test_command_is_enabled_explicitly() -> None:
    command = build_morning_preflight_scheduler_command(
        enabled=True
    )

    assert "app.run_morning_preflight_scheduler" in command
    assert "--enable" in command


def test_command_can_remain_disabled() -> None:
    command = build_morning_preflight_scheduler_command(
        enabled=False
    )

    assert "--enable" not in command
