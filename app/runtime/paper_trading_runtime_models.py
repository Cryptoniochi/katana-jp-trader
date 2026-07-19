"""終日Paper Trading Runtimeの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.application.trading_loop_models import (
    TradingLoopCycleResult,
)
from app.risk.risk_engine import RiskEngineResult
from app.trading.portfolio_models import PortfolioSnapshot


class PaperTradingRuntimeStatus(StrEnum):
    """終日Paper Trading Runtimeの状態。"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PaperTradingCycleRecord:
    """1回分のTrading Cycle・資産状態・リスク判定。"""

    cycle_result: TradingLoopCycleResult
    portfolio_snapshot: PortfolioSnapshot | None
    risk_result: RiskEngineResult | None = None

    @property
    def cycle_number(self) -> int:
        """サイクル番号を返す。"""

        return self.cycle_result.cycle_number

    @property
    def is_successful(self) -> bool:
        """サイクルが正常完了したか返す。"""

        return self.cycle_result.is_successful

    @property
    def has_risk_result(self) -> bool:
        """リスク判定結果を保持しているか返す。"""

        return self.risk_result is not None

    @property
    def allows_new_entries(self) -> bool | None:
        """新規エントリー可否を返す。"""

        if self.risk_result is None:
            return None

        return self.risk_result.allows_new_entries


@dataclass(frozen=True, slots=True)
class PaperTradingDailySummary:
    """1営業日のPaper Trading集計。"""

    trading_date: date
    started_at: datetime
    completed_at: datetime
    status: PaperTradingRuntimeStatus
    records: tuple[PaperTradingCycleRecord, ...]
    initial_equity: float | None
    final_equity: float | None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """日時・状態・サイクル番号を検証する。"""

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

        expected = list(
            range(1, len(self.records) + 1)
        )
        actual = [
            record.cycle_number
            for record in self.records
        ]

        if actual != expected:
            raise ValueError(
                "サイクル番号は1からの連番である必要があります。"
            )

        error_message = (
            None
            if self.error_message is None
            else self.error_message.strip() or None
        )

        if (
            self.status is PaperTradingRuntimeStatus.FAILED
            and error_message is None
        ):
            raise ValueError(
                "FAILED状態にはエラーメッセージが必要です。"
            )

        for name, value in {
            "初期純資産": self.initial_equity,
            "最終純資産": self.final_equity,
        }.items():
            if value is not None and value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        object.__setattr__(
            self,
            "error_message",
            error_message,
        )

    @property
    def cycle_count(self) -> int:
        """総サイクル数を返す。"""

        return len(self.records)

    @property
    def successful_cycle_count(self) -> int:
        """正常完了サイクル数を返す。"""

        return sum(
            record.is_successful
            for record in self.records
        )

    @property
    def failed_cycle_count(self) -> int:
        """失敗サイクル数を返す。"""

        return (
            self.cycle_count
            - self.successful_cycle_count
        )

    @property
    def signal_count(self) -> int:
        """シグナル数合計を返す。"""

        return sum(
            record.cycle_result.signal_count
            for record in self.records
        )

    @property
    def execution_count(self) -> int:
        """約定数合計を返す。"""

        return sum(
            record.cycle_result.execution_count
            for record in self.records
        )

    @property
    def risk_evaluated_cycle_count(self) -> int:
        """リスク判定済みサイクル数を返す。"""

        return sum(
            record.has_risk_result
            for record in self.records
        )

    @property
    def risk_blocked_cycle_count(self) -> int:
        """新規エントリー停止判定となったサイクル数を返す。"""

        return sum(
            record.allows_new_entries is False
            for record in self.records
        )

    @property
    def latest_risk_result(self) -> RiskEngineResult | None:
        """最新のリスク判定結果を返す。"""

        for record in reversed(self.records):
            if record.risk_result is not None:
                return record.risk_result

        return None

    @property
    def net_profit_loss(self) -> float | None:
        """初期純資産から最終純資産までの増減額を返す。"""

        if (
            self.initial_equity is None
            or self.final_equity is None
        ):
            return None

        return (
            self.final_equity - self.initial_equity
        )

    @property
    def return_rate(self) -> float | None:
        """日次リターン率を返す。"""

        if (
            self.initial_equity is None
            or self.final_equity is None
            or self.initial_equity == 0
        ):
            return None

        return (
            self.final_equity / self.initial_equity
            - 1.0
        )
