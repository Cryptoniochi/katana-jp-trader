"""Dashboard SnapshotをAtomic JSONとして保存する。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.dashboard.dashboard_json import (
    dashboard_snapshot_to_dict,
)
from app.dashboard.dashboard_models import DashboardSnapshot


@dataclass(frozen=True, slots=True)
class DashboardSnapshotWriteResult:
    """Dashboard Snapshotの保存結果。"""

    output_path: Path
    generated_at: datetime
    size_bytes: int

    def __post_init__(self) -> None:
        """保存結果を検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "Dashboard生成日時にはタイムゾーンが必要です。"
            )

        if self.size_bytes < 0:
            raise ValueError(
                "保存サイズは0以上である必要があります。"
            )


class DashboardSnapshotWriter:
    """Dashboard Snapshotを安全にJSON保存する。"""

    def __init__(
        self,
        *,
        output_path: Path,
    ) -> None:
        """出力先を設定する。"""

        self.output_path = Path(output_path)

    def write(
        self,
        snapshot: DashboardSnapshot | dict[str, Any],
    ) -> DashboardSnapshotWriteResult:
        """SnapshotをAtomic Writeで保存する。"""

        payload = self._to_payload(snapshot)
        generated_at = self._extract_generated_at(payload)

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.output_path.with_suffix(
            self.output_path.suffix + ".tmp"
        )
        serialized = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        try:
            temporary_path.write_text(
                serialized,
                encoding="utf-8",
                newline="\n",
            )
            os.replace(
                temporary_path,
                self.output_path,
            )
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        return DashboardSnapshotWriteResult(
            output_path=self.output_path,
            generated_at=generated_at,
            size_bytes=self.output_path.stat().st_size,
        )

    @staticmethod
    def _to_payload(
        snapshot: DashboardSnapshot | dict[str, Any],
    ) -> dict[str, Any]:
        """Domain Snapshotまたは辞書をJSON互換辞書へ変換する。"""

        if isinstance(snapshot, DashboardSnapshot):
            return dashboard_snapshot_to_dict(snapshot)

        if not isinstance(snapshot, dict):
            raise TypeError(
                "Dashboard SnapshotはDashboardSnapshotまたは"
                "dictである必要があります。"
            )

        return dict(snapshot)

    @staticmethod
    def _extract_generated_at(
        payload: dict[str, Any],
    ) -> datetime:
        """Payloadから生成日時を取得する。"""

        raw = payload.get("generated_at")

        if not isinstance(raw, str):
            raise ValueError(
                "Dashboard Snapshotにgenerated_atが必要です。"
            )

        generated_at = datetime.fromisoformat(raw)

        if generated_at.tzinfo is None:
            raise ValueError(
                "Dashboard生成日時にはタイムゾーンが必要です。"
            )

        return generated_at
