"""Runtime SessionをHealth Monitor入力へ変換する。"""

from __future__ import annotations

from typing import Protocol

from app.runtime.runtime_health_monitor_models import (
    RuntimeActivitySnapshot,
    RuntimeHealthMonitorReport,
)
from app.runtime.runtime_health_monitor_service import (
    RuntimeHealthMonitorService,
)
from app.runtime.session_models import RuntimeSessionSnapshot


class RuntimeSessionSnapshotReader(Protocol):
    def snapshot(self) -> RuntimeSessionSnapshot:
        """現在のRuntime Session Snapshotを返す。"""


class RuntimeHealthMonitorReader:
    """Runtime SessionとHealth Monitorを接続する。"""

    def __init__(
        self,
        *,
        session_reader: RuntimeSessionSnapshotReader,
        monitor_service: RuntimeHealthMonitorService,
    ) -> None:
        self.session_reader = session_reader
        self.monitor_service = monitor_service

    def check(self) -> RuntimeHealthMonitorReport:
        """現在のRuntime Healthを判定する。"""

        session = self.session_reader.snapshot()
        activity = RuntimeActivitySnapshot(
            checked_at=session.checked_at,
            running=session.is_running,
            started_at=session.started_at,
            last_heartbeat_at=session.last_heartbeat_at,
            last_cycle_at=session.last_cycle_at,
        )
        return self.monitor_service.evaluate(activity)
