"""長時間Trading Loop Runnerの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.trading_loop_models import (
    TradingLoopCycleResult,
)


class TradingLoopRunnerStopReason(StrEnum):
    """Trading Loop Runnerの終了理由。"""

    STOP_REQUESTED = "stop_requested"
    MAX_CYCLES_REACHED = "max_cycles_reached"
    RESOURCE_CRITICAL = "resource_critical"
    CYCLE_FAILED = "cycle_failed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TradingLoopRunnerSettings:
    """Trading Loop Runnerの実行設定。"""

    cycle_interval_seconds: float = 30.0
    maximum_cycles: int | None = None
    stop_on_cycle_failure: bool = False
    stop_on_resource_critical: bool = True

    def __post_init__(self) -> None:
        """実行設定を検証する。"""

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
class TradingLoopRunnerResult:
    """Trading Loop Runnerの全体実行結果。"""

    started_at: datetime
    completed_at: datetime
    stop_reason: TradingLoopRunnerStopReason
    cycles: tuple[TradingLoopCycleResult, ...]
    error_message: str | None = None

    def __post_init__(self) -> None:
        """日時・終了理由・サイクル番号を検証する。"""

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
            range(1, len(self.cycles) + 1)
        )
        actual = [
            cycle.cycle_number
            for cycle in self.cycles
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
            self.stop_reason is TradingLoopRunnerStopReason.ERROR
            and error_message is None
        ):
            raise ValueError(
                "ERROR終了にはエラーメッセージが必要です。"
            )

        object.__setattr__(
            self,
            "error_message",
            error_message,
        )

    @property
    def cycle_count(self) -> int:
        """総サイクル数を返す。"""

        return len(self.cycles)

    @property
    def successful_cycle_count(self) -> int:
        """正常完了サイクル数を返す。"""

        return sum(
            cycle.is_successful
            for cycle in self.cycles
        )

    @property
    def failed_cycle_count(self) -> int:
        """正常完了以外のサイクル数を返す。"""

        return (
            self.cycle_count
            - self.successful_cycle_count
        )
