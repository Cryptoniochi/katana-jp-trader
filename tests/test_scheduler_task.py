"""Windows Task Scheduler共通設定のテスト。"""

from pathlib import Path

import pytest

from app.scheduler_task import SchedulerTaskSettings


def test_task_settings_use_project_and_python(
    tmp_path: Path,
) -> None:
    python = tmp_path / "python.exe"
    python.write_text("", encoding="utf-8")
    project = tmp_path / "katana"
    project.mkdir()

    settings = SchedulerTaskSettings(
        task_name="Project KATANA",
        python_executable=python,
        project_root=project,
        start_time="8:05",
    )

    assert settings.start_time == "08:05"
    assert settings.python_executable == python.resolve()
    assert settings.project_root == project.resolve()
    assert settings.action_arguments == "-m app.scheduler"


@pytest.mark.parametrize(
    "start_time",
    [
        "",
        "8",
        "24:00",
        "10:60",
        "xx:yy",
    ],
)
def test_invalid_start_time_is_rejected(
    tmp_path: Path,
    start_time: str,
) -> None:
    python = tmp_path / "python.exe"
    python.write_text("", encoding="utf-8")
    project = tmp_path / "katana"
    project.mkdir()

    with pytest.raises(ValueError):
        SchedulerTaskSettings(
            task_name="Project KATANA",
            python_executable=python,
            project_root=project,
            start_time=start_time,
        )
