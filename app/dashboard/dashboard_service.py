"""Monitoring Dashboard用Snapshotを集約する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Protocol

from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardComponentError,
    DashboardOrderSummary,
    DashboardSnapshot,
)
from app.live.live_operation_log_models import (
    LiveDailyOperationSummary,
)
from app.monitoring.runtime_metrics import (
    RuntimeMetricsSnapshot,
)
from app.monitoring.system_health_models import (
    SystemHealthReport,
)
from app.trading.order_models import TradeOrderRecord
from app.trading.portfolio_models import PortfolioSnapshot


class DashboardSystemHealthReader(Protocol):
    """総合ヘルス取得処理。"""

    def check(self) -> SystemHealthReport:
        """現在の総合ヘルスを返す。"""


class DashboardRuntimeMetricsReader(Protocol):
    """ランタイムメトリクス取得処理。"""

    def snapshot(self) -> RuntimeMetricsSnapshot:
        """現在のメトリクスを返す。"""


class DashboardPortfolioReader(Protocol):
    """Portfolio取得処理。"""

    def create_snapshot(
        self,
        *,
        generated_at=None,
    ) -> PortfolioSnapshot:
        """現在のPortfolio Snapshotを返す。"""


class DashboardOrderReader(Protocol):
    """注文取得処理。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        status=None,
        side=None,
    ) -> list[TradeOrderRecord]:
        """注文一覧を返す。"""


class DashboardLiveSummaryReader(Protocol):
    """運用ログ日次集計取得処理。"""

    def summarize_date(
        self,
        target_date: date,
    ) -> LiveDailyOperationSummary:
        """指定日の運用サマリーを返す。"""


class DashboardBrokerReader(Protocol):
    """Broker状態取得処理。"""

    def get_dashboard_status(
        self,
    ) -> DashboardBrokerStatus:
        """Dashboard表示用Broker状態を返す。"""


class DashboardService:
    """複数情報源を部分成功モードで集約する。"""

    def __init__(
        self,
        *,
        system_health_reader: DashboardSystemHealthReader,
        runtime_metrics_reader: DashboardRuntimeMetricsReader,
        portfolio_reader: DashboardPortfolioReader,
        order_reader: DashboardOrderReader,
        live_summary_reader: DashboardLiveSummaryReader,
        broker_reader: DashboardBrokerReader,
        now_provider: Callable[[], datetime] | None = None,
        order_limit: int = 10_000,
    ) -> None:
        """依存関係と取得条件を設定する。"""

        if order_limit <= 0:
            raise ValueError(
                "注文取得件数は0より大きい必要があります。"
            )

        self.system_health_reader = system_health_reader
        self.runtime_metrics_reader = runtime_metrics_reader
        self.portfolio_reader = portfolio_reader
        self.order_reader = order_reader
        self.live_summary_reader = live_summary_reader
        self.broker_reader = broker_reader
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.order_limit = order_limit

    def create_snapshot(
        self,
    ) -> DashboardSnapshot:
        """現在のDashboard Snapshotを返す。"""

        generated_at = self._current_time()
        errors: list[DashboardComponentError] = []

        system_health = self._read_component(
            "system_health",
            self.system_health_reader.check,
            errors,
        )
        runtime_metrics = self._read_component(
            "runtime_metrics",
            self.runtime_metrics_reader.snapshot,
            errors,
        )
        portfolio = self._read_component(
            "portfolio",
            self.portfolio_reader.create_snapshot,
            errors,
        )
        order_records = self._read_component(
            "orders",
            lambda: tuple(
                self.order_reader.list_recent(
                    limit=self.order_limit,
                )
            ),
            errors,
        )
        live_summary = self._read_component(
            "live_summary",
            lambda: self.live_summary_reader.summarize_date(
                generated_at.date()
            ),
            errors,
        )
        broker = self._read_component(
            "broker",
            self.broker_reader.get_dashboard_status,
            errors,
        )

        orders = (
            DashboardOrderSummary.from_records(
                order_records
            )
            if order_records is not None
            else None
        )

        return DashboardSnapshot(
            generated_at=generated_at,
            system_health=system_health,
            runtime_metrics=runtime_metrics,
            portfolio=portfolio,
            orders=orders,
            live_summary=live_summary,
            broker=broker,
            errors=tuple(errors),
        )

    @staticmethod
    def _read_component(
        component: str,
        reader,
        errors: list[DashboardComponentError],
    ):
        """1構成要素を取得し、失敗時は記録してNoneを返す。"""

        try:
            return reader()

        except Exception as error:
            errors.append(
                DashboardComponentError(
                    component=component,
                    error_message=(
                        str(error).strip()
                        or type(error).__name__
                    ),
                )
            )
            return None

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
