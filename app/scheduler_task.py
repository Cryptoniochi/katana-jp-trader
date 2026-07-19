"""Windows Task Scheduler登録情報の共通処理。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


DEFAULT_TASK_NAME = "Project KATANA Paper Trading"
DEFAULT_START_TIME = "08:55"


@dataclass(frozen=True, slots=True)
class SchedulerTaskSettings:
    """Windowsタスク登録に必要な設定。"""

    task_name: str
    python_executable: Path
    project_root: Path
    start_time: str = DEFAULT_START_TIME
    weekdays: tuple[str, ...] = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    )

    def __post_init__(self) -> None:
        """登録設定を検証して正規化する。"""

        task_name = self.task_name.strip()
        python_executable = Path(
            self.python_executable
        ).resolve()
        project_root = Path(
            self.project_root
        ).resolve()
        start_time = self.start_time.strip()

        if not task_name:
            raise ValueError(
                "タスク名を指定してください。"
            )

        if not python_executable.is_file():
            raise ValueError(
                "Python実行ファイルが見つかりません。 "
                f"path={python_executable}"
            )

        if not project_root.is_dir():
            raise ValueError(
                "プロジェクトルートが見つかりません。 "
                f"path={project_root}"
            )

        parts = start_time.split(":")

        if len(parts) != 2:
            raise ValueError(
                "開始時刻はHH:MM形式で指定してください。"
            )

        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError as error:
            raise ValueError(
                "開始時刻はHH:MM形式で指定してください。"
            ) from error

        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError(
                "開始時刻が範囲外です。"
            )

        weekdays = tuple(
            dict.fromkeys(
                day.strip()
                for day in self.weekdays
                if day.strip()
            )
        )

        allowed = {
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        }

        if not weekdays:
            raise ValueError(
                "実行曜日を1件以上指定してください。"
            )

        if any(day not in allowed for day in weekdays):
            raise ValueError(
                "実行曜日に不正な値があります。"
            )

        object.__setattr__(
            self,
            "task_name",
            task_name,
        )
        object.__setattr__(
            self,
            "python_executable",
            python_executable,
        )
        object.__setattr__(
            self,
            "project_root",
            project_root,
        )
        object.__setattr__(
            self,
            "start_time",
            f"{hour:02d}:{minute:02d}",
        )
        object.__setattr__(
            self,
            "weekdays",
            weekdays,
        )

    @property
    def action_arguments(self) -> str:
        """Pythonへ渡す引数を返す。"""

        return "-m app.scheduler"


def default_scheduler_task_settings(
    *,
    task_name: str = DEFAULT_TASK_NAME,
    start_time: str = DEFAULT_START_TIME,
) -> SchedulerTaskSettings:
    """現在の実行環境から既定登録設定を生成する。"""

    project_root = Path(__file__).resolve().parents[1]

    return SchedulerTaskSettings(
        task_name=task_name,
        python_executable=Path(sys.executable),
        project_root=project_root,
        start_time=start_time,
    )
