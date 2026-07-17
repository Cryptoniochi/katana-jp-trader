"""DashboardSnapshotをJSONファイルへ安全に保存する。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.dashboard.dashboard_json import (
    dashboard_snapshot_to_dict,
)
from app.dashboard.dashboard_models import DashboardSnapshot


@dataclass(frozen=True, slots=True)
class DashboardExportResult:
    """Dashboard JSON保存結果。"""

    latest_path: Path
    history_path: Path | None
    bytes_written: int

    def __post_init__(self) -> None:
        """保存結果を検証する。"""

        if self.bytes_written <= 0:
            raise ValueError(
                "書き込みバイト数は0より大きい必要があります。"
            )


class DashboardExporter:
    """Latest JSONと履歴JSONを原子的に保存する。"""

    def __init__(
        self,
        *,
        output_directory: Path,
        latest_filename: str = "dashboard.json",
        save_history: bool = True,
    ) -> None:
        """出力先と履歴保存方針を設定する。"""

        latest_filename = latest_filename.strip()

        if not latest_filename:
            raise ValueError(
                "最新Dashboardファイル名を指定してください。"
            )

        if Path(latest_filename).name != latest_filename:
            raise ValueError(
                "最新Dashboardファイル名には"
                "ディレクトリを含められません。"
            )

        self.output_directory = output_directory
        self.latest_filename = latest_filename
        self.save_history = save_history

    def export(
        self,
        snapshot: DashboardSnapshot,
    ) -> DashboardExportResult:
        """Dashboard SnapshotをJSONへ保存する。"""

        self.output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = dashboard_snapshot_to_dict(snapshot)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        encoded = serialized.encode("utf-8")

        latest_path = (
            self.output_directory
            / self.latest_filename
        )
        self._atomic_write(
            latest_path,
            encoded,
        )

        history_path: Path | None = None

        if self.save_history:
            timestamp = snapshot.generated_at.strftime(
                "%Y%m%dT%H%M%S%fZ"
            )
            history_path = (
                self.output_directory
                / f"dashboard_{timestamp}.json"
            )
            self._atomic_write(
                history_path,
                encoded,
            )

        return DashboardExportResult(
            latest_path=latest_path,
            history_path=history_path,
            bytes_written=len(encoded),
        )

    @staticmethod
    def _atomic_write(
        path: Path,
        content: bytes,
    ) -> None:
        """一時ファイル経由で原子的に置き換える。"""

        temporary_path = path.with_name(
            f".{path.name}.tmp"
        )

        try:
            temporary_path.write_bytes(content)
            os.replace(
                temporary_path,
                path,
            )
        except Exception:
            temporary_path.unlink(
                missing_ok=True,
            )
            raise
