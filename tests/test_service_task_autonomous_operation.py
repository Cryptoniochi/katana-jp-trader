"""Windows Service taskの自律運転設定テスト。"""

from pathlib import Path


def test_service_task_enables_both_schedules() -> None:
    content = Path(
        "scripts/run_katana_service_task.cmd"
    ).read_text(
        encoding="utf-8"
    )

    assert "--enable-paper-trading-schedule" in content
    assert "--enable-daily-report-schedule" in content
    assert "--enable-paper-trading " not in content
