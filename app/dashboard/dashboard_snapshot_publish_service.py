"""Dashboard Snapshotの生成と保存を一体化する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.dashboard.dashboard_models import DashboardSnapshot
from app.dashboard.dashboard_snapshot_writer import (
    DashboardSnapshotWriteResult,
)


class DashboardSnapshotProvider(Protocol):
    """現在のDashboard Snapshotを提供する。"""

    def create_snapshot(self) -> DashboardSnapshot:
        """現在状態を集約して返す。"""


class DashboardSnapshotOutput(Protocol):
    """Dashboard Snapshotを保存する。"""

    def write(
        self,
        snapshot: DashboardSnapshot,
    ) -> DashboardSnapshotWriteResult:
        """Snapshotを保存する。"""


@dataclass(frozen=True, slots=True)
class DashboardSnapshotPublishResult:
    """Dashboard Snapshot生成・保存結果。"""

    snapshot: DashboardSnapshot
    write_result: DashboardSnapshotWriteResult


class DashboardSnapshotPublishService:
    """Dashboard ServiceからSnapshotを生成してJSON保存する。"""

    def __init__(
        self,
        *,
        snapshot_provider: DashboardSnapshotProvider,
        snapshot_writer: DashboardSnapshotOutput,
    ) -> None:
        """ProviderとWriterを設定する。"""

        self.snapshot_provider = snapshot_provider
        self.snapshot_writer = snapshot_writer

    def publish(self) -> DashboardSnapshotPublishResult:
        """現在Snapshotを生成して保存する。"""

        snapshot = self.snapshot_provider.create_snapshot()
        write_result = self.snapshot_writer.write(snapshot)

        return DashboardSnapshotPublishResult(
            snapshot=snapshot,
            write_result=write_result,
        )
