"""終日Paper Trading運用の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
)


class PaperTradingDayStopReason(StrEnum):
    """終日Paper Trading運用の終了理由。"""

    MARKET_CLOSED = "market_closed"
    STOP_REQUESTED = "stop_requested"
    MAX_CYCLES_REACHED = "max_cycles_reached"
    RESOURCE_CRITICAL = "resource_critical"
    CYCLE_FAILED = "cycle_failed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PaperTradingDaySettings:
    """終日Paper Trading運用の設定。"""

    cycle_interval_seconds: float = 30.0
    maximum_cycles: int | None = None
    stop_on_cycle_failure: bool = False
    stop_on_resource_critical: bool = True
    continue_on_dashboard_error: bool = True
    continue_on_post_run_hook_error: bool = True

    def __post_init__(self) -> None:
        """設定値を検証する。"""

        if self.cycle_interval_seconds < 0:
            raise ValueError(
                "サイクル間隔は0秒以上である必要があります。"
            )

        if (
            self.maximum_cycles is not None
            and self.maximum_cycles <= 0
        ):
            raise ValueError(
                "最大サイクル数は0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class PaperTradingDayResult:
    """1営業日の運用・集計・永続化結果。"""

    trading_date: date
    started_at: datetime
    completed_at: datetime
    stop_reason: PaperTradingDayStopReason
    summary: PaperTradingDailySummary
    record: PaperTradingDailyRecord
    error_message: str | None = None
    dashboard_published: bool = False
    dashboard_error_message: str | None = None
    completed_post_run_hook_count: int = 0
    post_run_hook_error_messages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """日時・営業日・後処理結果を検証する。"""

        for name, value in {
            "開始日時": self.started_at,
            "完了日時": self.completed_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.completed_at < self.started_at:
            raise ValueError(
                "完了日時は開始日時以後である必要があります。"
            )

        if self.summary.trading_date != self.trading_date:
            raise ValueError(
                "Summaryの営業日が運用結果と一致しません。"
            )

        if self.record.trading_date != self.trading_date:
            raise ValueError(
                "保存レコードの営業日が運用結果と一致しません。"
            )

        if self.completed_post_run_hook_count < 0:
            raise ValueError(
                "完了Post-run Hook数は0以上である必要があります。"
            )

        error_message = (
            None
            if self.error_message is None
            else self.error_message.strip() or None
        )
        dashboard_error_message = (
            None
            if self.dashboard_error_message is None
            else self.dashboard_error_message.strip() or None
        )
        hook_errors = tuple(
            message.strip()
            for message in self.post_run_hook_error_messages
            if message.strip()
        )

        if (
            self.stop_reason is PaperTradingDayStopReason.ERROR
            and error_message is None
        ):
            raise ValueError(
                "ERROR終了にはエラーメッセージが必要です。"
            )

        if (
            self.dashboard_published
            and dashboard_error_message is not None
        ):
            raise ValueError(
                "Dashboard公開成功時にエラーは設定できません。"
            )

        object.__setattr__(
            self,
            "error_message",
            error_message,
        )
        object.__setattr__(
            self,
            "dashboard_error_message",
            dashboard_error_message,
        )
        object.__setattr__(
            self,
            "post_run_hook_error_messages",
            hook_errors,
        )

    @property
    def cycle_count(self) -> int:
        """総サイクル数を返す。"""

        return self.summary.cycle_count

    @property
    def net_profit_loss(self) -> float | None:
        """日次損益を返す。"""

        return self.summary.net_profit_loss

    @property
    def return_rate(self) -> float | None:
        """日次リターン率を返す。"""

        return self.summary.return_rate

    @property
    def post_run_hook_failure_count(self) -> int:
        """失敗したPost-run Hook数を返す。"""

        return len(self.post_run_hook_error_messages)
