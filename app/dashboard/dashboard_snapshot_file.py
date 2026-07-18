"""Dashboard latest JSONをRead-onlyで読み込む。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DashboardJsonSnapshotReader:
    """Dashboard JSONファイルをWeb表示用に提供する。"""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        now_provider=None,
    ) -> None:
        """JSON Pathと時計を設定する。"""

        self.snapshot_path = Path(snapshot_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def create_snapshot(self) -> dict[str, Any]:
        """最新Snapshotを辞書として返す。"""

        if not self.snapshot_path.exists():
            return self._unavailable_snapshot(
                "Dashboard JSONがまだ生成されていません。 "
                f"path={self.snapshot_path}"
            )

        try:
            raw = self.snapshot_path.read_text(
                encoding="utf-8"
            )
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            return self._unavailable_snapshot(
                "Dashboard JSONを読み込めませんでした。 "
                f"error={str(error).strip() or type(error).__name__}"
            )

        if not isinstance(payload, dict):
            return self._unavailable_snapshot(
                "Dashboard JSONのルートは辞書形式である必要があります。"
            )

        normalized = dict(payload)
        normalized.setdefault(
            "generated_at",
            self._current_time().isoformat(),
        )
        normalized.setdefault("complete", False)
        normalized.setdefault("partial", True)
        normalized.setdefault("errors", [])
        normalized.setdefault("system_health", None)
        normalized.setdefault("runtime_metrics", None)
        normalized.setdefault("runtime_resource", None)
        normalized.setdefault("portfolio", None)
        normalized.setdefault("orders", None)
        normalized.setdefault("live_summary", None)
        normalized.setdefault("broker", None)

        return normalized

    def _unavailable_snapshot(
        self,
        message: str,
    ) -> dict[str, Any]:
        """未生成・破損時の安全な部分Snapshotを返す。"""

        return {
            "generated_at": self._current_time().isoformat(),
            "complete": False,
            "partial": True,
            "errors": [
                {
                    "component": "dashboard_snapshot_file",
                    "error_message": message,
                }
            ],
            "system_health": None,
            "runtime_metrics": None,
            "runtime_resource": None,
            "portfolio": None,
            "orders": None,
            "live_summary": None,
            "broker": None,
        }

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
