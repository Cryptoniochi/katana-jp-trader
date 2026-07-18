"""Monitoring Dashboardの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_operation_log_models import (
    LiveDailyOperationSummary,
)
from app.monitoring.runtime_metrics import (
    RuntimeMetricsSnapshot,
)
from app.monitoring.system_health_models import (
    SystemHealthReport,
)
from app.runtime.resource_models import (
    RuntimeResourceEvaluation,
)
from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
)
from app.trading.order_models import (
    OrderStatus,
    TradeOrderRecord,
)
from app.trading.portfolio_models import (
    PortfolioSnapshot,
)


class DashboardComponentStatus(StrEnum):
    """Dashboard構成要素の取得状態。"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DashboardComponentError:
    """Dashboard構成要素の取得エラー。"""

    component: str
    error_message: str

    def __post_init__(self) -> None:
        """エラー内容を検証して正規化する。"""

        component = self.component.strip()
        error_message = self.error_message.strip()

        if not component:
            raise ValueError(
                "Dashboard構成要素名を指定してください。"
            )

        if not error_message:
            raise ValueError(
                "Dashboardエラーメッセージを指定してください。"
            )

        object.__setattr__(
            self,
            "component",
            component,
        )
        object.__setattr__(
            self,
            "error_message",
            error_message,
        )


@dataclass(frozen=True, slots=True)
class DashboardOrderSummary:
    """注文状態の件数集計。"""

    total_count: int
    active_count: int
    terminal_count: int
    status_counts: dict[OrderStatus, int]

    def __post_init__(self) -> None:
        """注文件数の整合性を検証する。"""

        if self.total_count < 0:
            raise ValueError(
                "注文件数は0以上である必要があります。"
            )

        if self.active_count < 0:
            raise ValueError(
                "有効注文件数は0以上である必要があります。"
            )

        if self.terminal_count < 0:
            raise ValueError(
                "終了注文件数は0以上である必要があります。"
            )

        if (
            self.active_count + self.terminal_count
            != self.total_count
        ):
            raise ValueError(
                "有効注文と終了注文の合計が"
                "注文件数と一致しません。"
            )

        normalized = {
            OrderStatus(status): int(count)
            for status, count in self.status_counts.items()
        }

        if any(count < 0 for count in normalized.values()):
            raise ValueError(
                "注文状態別件数は0以上である必要があります。"
            )

        for status in OrderStatus:
            normalized.setdefault(status, 0)

        if sum(normalized.values()) != self.total_count:
            raise ValueError(
                "注文状態別件数の合計が"
                "注文件数と一致しません。"
            )

        object.__setattr__(
            self,
            "status_counts",
            dict(normalized),
        )

    @classmethod
    def from_records(
        cls,
        records: tuple[TradeOrderRecord, ...],
    ) -> "DashboardOrderSummary":
        """注文一覧から件数集計を作成する。"""

        status_counts = {
            status: 0
            for status in OrderStatus
        }

        for record in records:
            status_counts[record.status] += 1

        active_count = sum(
            count
            for status, count in status_counts.items()
            if status.is_active
        )

        terminal_count = sum(
            count
            for status, count in status_counts.items()
            if status.is_terminal
        )

        return cls(
            total_count=len(records),
            active_count=active_count,
            terminal_count=terminal_count,
            status_counts=status_counts,
        )


@dataclass(frozen=True, slots=True)
class DashboardBrokerStatus:
    """Dashboard表示用Broker状態。"""

    connected: bool
    name: str
    message: str | None = None

    def __post_init__(self) -> None:
        """Broker状態を検証して正規化する。"""

        name = self.name.strip()
        message = (
            None
            if self.message is None
            else self.message.strip()
        )

        if not name:
            raise ValueError(
                "Broker名を指定してください。"
            )

        if not self.connected and not message:
            raise ValueError(
                "Broker切断時にはメッセージが必要です。"
            )

        object.__setattr__(self, "name", name)
        object.__setattr__(
            self,
            "message",
            message or None,
        )


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """Monitoring Dashboardの集約Snapshot。"""

    generated_at: datetime
    system_health: SystemHealthReport | None
    runtime_metrics: RuntimeMetricsSnapshot | None
    portfolio: PortfolioSnapshot | None
    orders: DashboardOrderSummary | None
    live_summary: LiveDailyOperationSummary | None
    broker: DashboardBrokerStatus | None
    errors: tuple[DashboardComponentError, ...]
    runtime_resource: RuntimeResourceEvaluation | None = None
    runtime_health: RuntimeHealthMonitorReport | None = None

    def __post_init__(self) -> None:
        """Snapshotの基本整合性を検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "Dashboard生成日時にはタイムゾーンが必要です。"
            )

    @property
    def is_complete(self) -> bool:
        """全構成要素を取得できたか返す。"""

        return not self.errors

    @property
    def is_partial(self) -> bool:
        """一部取得失敗があるか返す。"""

        return bool(self.errors)

    @property
    def unavailable_components(self) -> tuple[str, ...]:
        """取得できなかった構成要素名を返す。"""

        return tuple(
            error.component
            for error in self.errors
        )
