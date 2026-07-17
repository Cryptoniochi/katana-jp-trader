"""インメモリでランタイム運用メトリクスを集計する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock

from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
    RuntimeMetricsSnapshot,
)


class RuntimeMetricsService:
    """スレッド安全な累積カウンターを管理する。"""

    def __init__(
        self,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """時計・カウンター・ロックを初期化する。"""

        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._counts = {
            metric: 0
            for metric in RuntimeMetricName
        }
        self._lock = Lock()

    def increment(
        self,
        metric: RuntimeMetricName,
        *,
        amount: int = 1,
    ) -> int:
        """指定メトリクスを加算し、更新後の値を返す。"""

        if amount <= 0:
            raise ValueError(
                "加算値は0より大きい必要があります。"
            )

        with self._lock:
            self._counts[metric] += amount
            return self._counts[metric]

    def get(
        self,
        metric: RuntimeMetricName,
    ) -> int:
        """指定メトリクスの現在値を返す。"""

        with self._lock:
            return self._counts[metric]

    def snapshot(self) -> RuntimeMetricsSnapshot:
        """現在値をSnapshotとして返す。"""

        generated_at = self._current_time()

        with self._lock:
            counts = dict(self._counts)

        return RuntimeMetricsSnapshot(
            generated_at=generated_at,
            counts=counts,
        )

    def reset(
        self,
        *,
        metric: RuntimeMetricName | None = None,
    ) -> None:
        """指定または全メトリクスを0へ戻す。"""

        with self._lock:
            if metric is None:
                for item in self._counts:
                    self._counts[item] = 0
                return

            self._counts[metric] = 0

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
