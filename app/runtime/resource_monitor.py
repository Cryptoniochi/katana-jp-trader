"""Runtime Resourceを取得・評価・履歴保存する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.runtime.resource_models import (
    RuntimeResourceEvaluation,
    RuntimeResourceSnapshot,
    RuntimeResourceThresholds,
)


class RuntimeProcessReader(Protocol):
    """現在プロセスのリソース情報を提供する。"""

    def cpu_percent(self) -> float:
        """CPU使用率を返す。"""

    def memory_info(self):
        """rss・vms属性を持つメモリ情報を返す。"""

    def num_threads(self) -> int:
        """スレッド数を返す。"""

    def create_time(self) -> float:
        """プロセス開始時刻をUnix秒で返す。"""


@dataclass(frozen=True, slots=True)
class RuntimeResourceHistorySummary:
    """サンプリング履歴の統計情報。"""

    sample_count: int
    average_cpu_percent: float
    maximum_cpu_percent: float
    average_rss_bytes: float
    maximum_rss_bytes: int
    maximum_vms_bytes: int
    maximum_thread_count: int
    latest: RuntimeResourceEvaluation | None

    def __post_init__(self) -> None:
        """履歴統計の整合性を検証する。"""

        if self.sample_count < 0:
            raise ValueError(
                "サンプル数は0以上である必要があります。"
            )

        if self.sample_count == 0 and self.latest is not None:
            raise ValueError(
                "空履歴には最新評価を設定できません。"
            )

        if self.sample_count > 0 and self.latest is None:
            raise ValueError(
                "履歴ありの場合は最新評価が必要です。"
            )


class RuntimeResourceHistory:
    """固定件数のリソース評価履歴を保持する。"""

    def __init__(
        self,
        *,
        maximum_samples: int = 1000,
    ) -> None:
        """最大保持件数を設定する。"""

        if maximum_samples <= 0:
            raise ValueError(
                "最大保持件数は0より大きい必要があります。"
            )

        self.maximum_samples = maximum_samples
        self._items: list[RuntimeResourceEvaluation] = []

    def append(
        self,
        evaluation: RuntimeResourceEvaluation,
    ) -> None:
        """評価結果を履歴へ追加する。"""

        self._items.append(evaluation)

        overflow = len(self._items) - self.maximum_samples

        if overflow > 0:
            del self._items[:overflow]

    def items(
        self,
    ) -> tuple[RuntimeResourceEvaluation, ...]:
        """履歴を不変タプルで返す。"""

        return tuple(self._items)

    def clear(self) -> None:
        """履歴を消去する。"""

        self._items.clear()

    def summary(self) -> RuntimeResourceHistorySummary:
        """現在履歴の統計情報を返す。"""

        if not self._items:
            return RuntimeResourceHistorySummary(
                sample_count=0,
                average_cpu_percent=0.0,
                maximum_cpu_percent=0.0,
                average_rss_bytes=0.0,
                maximum_rss_bytes=0,
                maximum_vms_bytes=0,
                maximum_thread_count=0,
                latest=None,
            )

        snapshots = [
            item.snapshot
            for item in self._items
        ]
        sample_count = len(snapshots)

        return RuntimeResourceHistorySummary(
            sample_count=sample_count,
            average_cpu_percent=(
                sum(item.cpu_percent for item in snapshots)
                / sample_count
            ),
            maximum_cpu_percent=max(
                item.cpu_percent
                for item in snapshots
            ),
            average_rss_bytes=(
                sum(item.rss_bytes for item in snapshots)
                / sample_count
            ),
            maximum_rss_bytes=max(
                item.rss_bytes
                for item in snapshots
            ),
            maximum_vms_bytes=max(
                item.vms_bytes
                for item in snapshots
            ),
            maximum_thread_count=max(
                item.thread_count
                for item in snapshots
            ),
            latest=self._items[-1],
        )


class RuntimeResourceMonitorService:
    """現在プロセスをサンプリングして閾値評価する。"""

    def __init__(
        self,
        *,
        process_reader: RuntimeProcessReader,
        thresholds: RuntimeResourceThresholds | None = None,
        history: RuntimeResourceHistory | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """依存関係・閾値・履歴・時計を設定する。"""

        self.process_reader = process_reader
        self.thresholds = (
            thresholds
            if thresholds is not None
            else RuntimeResourceThresholds()
        )
        self.history = (
            history
            if history is not None
            else RuntimeResourceHistory()
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def sample(self) -> RuntimeResourceEvaluation:
        """現在プロセスを1回サンプリングする。"""

        sampled_at = self._current_time()
        memory = self.process_reader.memory_info()
        process_started_at = datetime.fromtimestamp(
            self.process_reader.create_time(),
            tz=timezone.utc,
        )
        uptime_seconds = max(
            0.0,
            (
                sampled_at - process_started_at
            ).total_seconds(),
        )

        snapshot = RuntimeResourceSnapshot(
            sampled_at=sampled_at,
            cpu_percent=float(
                self.process_reader.cpu_percent()
            ),
            rss_bytes=int(memory.rss),
            vms_bytes=int(memory.vms),
            thread_count=int(
                self.process_reader.num_threads()
            ),
            process_uptime_seconds=uptime_seconds,
        )
        evaluation = snapshot.evaluate(
            self.thresholds
        )
        self.history.append(evaluation)

        return evaluation

    def latest(
        self,
    ) -> RuntimeResourceEvaluation | None:
        """最新評価を返す。"""

        items = self.history.items()
        return items[-1] if items else None

    def history_summary(
        self,
    ) -> RuntimeResourceHistorySummary:
        """履歴統計を返す。"""

        return self.history.summary()

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
