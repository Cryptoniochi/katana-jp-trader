"""KATANA Service Manager状態ファイルを読み込む。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class KatanaServiceStatusReadError(RuntimeError):
    """Service状態ファイルを読み込めないことを表す。"""


class KatanaServiceStatusReader:
    """Service Managerが出力したJSON状態をDashboardへ渡す。"""

    def __init__(
        self,
        status_path: Path,
    ) -> None:
        self.status_path = Path(status_path)

    def read(self) -> dict[str, Any]:
        """現在状態を読み込み、未生成時は安全な空状態を返す。"""

        if not self.status_path.exists():
            return self._empty_payload(
                message=(
                    "Service Manager status file "
                    "has not been created."
                )
            )

        try:
            payload = json.loads(
                self.status_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            raise KatanaServiceStatusReadError(
                "KATANA Service状態を読み込めませんでした。 "
                f"path={self.status_path}"
            ) from error

        if not isinstance(payload, dict):
            raise KatanaServiceStatusReadError(
                "KATANA Service状態は辞書形式である必要があります。"
            )

        components = payload.get(
            "components",
            [],
        )

        if not isinstance(components, list):
            raise KatanaServiceStatusReadError(
                "componentsは配列形式である必要があります。"
            )

        return {
            "available": True,
            "generated_at": payload.get(
                "generated_at"
            ),
            "service_state": payload.get(
                "service_state",
                "unknown",
            ),
            "kabu_station_readiness": payload.get(
                "kabu_station_readiness",
                "unknown",
            ),
            "components": [
                self._normalize_component(item)
                for item in components
                if isinstance(item, dict)
            ],
            "message": None,
        }

    @staticmethod
    def _normalize_component(
        item: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "name": str(
                item.get(
                    "name",
                    "unknown",
                )
            ),
            "state": str(
                item.get(
                    "state",
                    "unknown",
                )
            ),
            "enabled": bool(
                item.get(
                    "enabled",
                    False,
                )
            ),
            "process_id": item.get(
                "process_id"
            ),
            "restart_count": int(
                item.get(
                    "restart_count",
                    0,
                )
            ),
            "last_exit_code": item.get(
                "last_exit_code"
            ),
            "started_at": item.get(
                "started_at"
            ),
            "updated_at": item.get(
                "updated_at"
            ),
            "message": item.get(
                "message"
            ),
        }

    @staticmethod
    def _empty_payload(
        *,
        message: str,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "service_state": "not_running",
            "kabu_station_readiness": "not_checked",
            "components": [],
            "message": message,
        }
