"""Project KATANAの設定管理。"""

from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """アプリケーション全体の設定。"""

    app_name: str = "Project KATANA"
    version: str = "0.19.0"

    data_dir: Path = ROOT_DIR / "data"
    logs_dir: Path = ROOT_DIR / "logs"
    reports_dir: Path = ROOT_DIR / "reports"

    csv_dir: Path = ROOT_DIR / "data" / "csv"
    historical_csv_dir: Path = ROOT_DIR / "data" / "historical"

    database_path: Path = ROOT_DIR / "data" / "katana.db"

    def create_directories(self) -> None:
        """必要なフォルダを作成する。"""

        self.data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.logs_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.reports_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.csv_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.historical_csv_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


settings = Settings()
