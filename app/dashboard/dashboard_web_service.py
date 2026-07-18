"""既存Dashboardと日次RepositoryをWeb表示用に集約する。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.dashboard.dashboard_json import (
    dashboard_snapshot_to_dict,
)
from app.dashboard.dashboard_models import DashboardSnapshot
from app.dashboard.dashboard_web_models import (
    DashboardDailyPoint,
    DashboardWebPayload,
)
from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)


class DashboardSnapshotReader(Protocol):
    """現在Dashboard SnapshotのRead-only Provider。"""

    def create_snapshot(
        self,
    ) -> DashboardSnapshot | dict[str, Any]:
        """現在Snapshotを返す。"""


class DashboardDailyHistoryReader(Protocol):
    """Paper Trading日次履歴のRead-only Provider。"""

    def list_recent(
        self,
        *,
        limit: int = 30,
    ) -> tuple[PaperTradingDailyRecord, ...]:
        """新しい営業日順で日次履歴を返す。"""


class DashboardWebService:
    """Web Dashboard v1の表示データを作成する。"""

    def __init__(
        self,
        *,
        snapshot_reader: DashboardSnapshotReader,
        daily_history_reader: DashboardDailyHistoryReader,
        history_limit: int = 30,
    ) -> None:
        """Read-only Providerと履歴件数を設定する。"""

        if history_limit <= 0:
            raise ValueError(
                "日次履歴件数は0より大きい必要があります。"
            )

        self.snapshot_reader = snapshot_reader
        self.daily_history_reader = daily_history_reader
        self.history_limit = history_limit

    def create_payload(self) -> DashboardWebPayload:
        """現在状態と日次推移を集約する。"""

        snapshot = self.snapshot_reader.create_snapshot()
        snapshot_payload = self._snapshot_to_dict(snapshot)
        generated_at = self._extract_generated_at(
            snapshot,
            snapshot_payload,
        )

        recent_records = self.daily_history_reader.list_recent(
            limit=self.history_limit
        )
        chronological = tuple(reversed(recent_records))

        daily_history = tuple(
            DashboardDailyPoint(
                trading_date=record.trading_date,
                net_profit_loss=record.net_profit_loss,
                final_equity=record.final_equity,
                return_rate=record.return_rate,
            )
            for record in chronological
        )

        cumulative_profit_loss = sum(
            record.net_profit_loss or 0.0
            for record in chronological
        )

        return DashboardWebPayload(
            generated_at=generated_at,
            snapshot=snapshot_payload,
            daily_history=daily_history,
            cumulative_profit_loss=cumulative_profit_loss,
        )

    @staticmethod
    def _snapshot_to_dict(
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
        snapshot: DashboardSnapshot | dict[str, Any],
        payload: dict[str, Any],
    ) -> datetime:
        """Snapshot生成日時を取得する。"""

        if isinstance(snapshot, DashboardSnapshot):
            return snapshot.generated_at

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
