"""市場スケジューラの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.live.live_orchestrator_models import (
    LiveCycleResult,
)


class MarketSchedulerStopReason(StrEnum):
    """市場スケジューラの終了理由。"""

    STOP_REQUESTED = "stop_requested"
    NON_TRADING_DAY = "non_trading_day"
    MARKET_CLOSED = "market_closed"
    MAX_CYCLES_REACHED = "max_cycles_reached"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MarketSchedulerSettings:
    """市場スケジューラの実行設定。"""

    trading_poll_interval_seconds: float = 30.0
    idle_poll_interval_seconds: float = 60.0
    max_cycles: int | None = None
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        """設定値を検証する。"""

        if self.trading_poll_interval_seconds < 0:
            raise ValueError(
                "取引時間中のポーリング間隔は"
                "0秒以上である必要があります。"
            )

        if self.idle_poll_interval_seconds <= 0:
            raise ValueError(
                "待機中のポーリング間隔は"
                "0秒より大きい必要があります。"
            )

        if (
            self.max_cycles is not None
            and self.max_cycles <= 0
        ):
            raise ValueError(
                "最大サイクル数は0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class MarketSchedulerResult:
    """市場スケジューラの1回の運転結果。"""

    started_at: datetime
    completed_at: datetime
    trading_date: date
    stop_reason: MarketSchedulerStopReason
    cycles: tuple[LiveCycleResult, ...]
    sleep_count: int
    slept_seconds: float
    error_message: str | None = None

    def __post_init__(self) -> None:
        """日時・件数・終了理由の整合性を検証する。"""

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

        if self.sleep_count < 0:
            raise ValueError(
                "待機回数は0以上である必要があります。"
            )

        if self.slept_seconds < 0:
            raise ValueError(
                "待機秒数は0以上である必要があります。"
            )

        expected_cycle_numbers = list(
            range(1, len(self.cycles) + 1)
        )
        actual_cycle_numbers = [
            cycle.cycle_number
            for cycle in self.cycles
        ]

        if actual_cycle_numbers != expected_cycle_numbers:
            raise ValueError(
                "サイクル番号は1からの連番である必要があります。"
            )

        normalized_error = (
            None
            if self.error_message is None
            else self.error_message.strip()
        )

        if (
            self.stop_reason
            is MarketSchedulerStopReason.ERROR
            and not normalized_error
        ):
            raise ValueError(
                "エラー終了時には"
                "エラーメッセージが必要です。"
            )

        if (
            self.stop_reason
            is not MarketSchedulerStopReason.ERROR
            and normalized_error
        ):
            raise ValueError(
                "正常終了結果には"
                "エラーメッセージを設定できません。"
            )

        object.__setattr__(
            self,
            "error_message",
            normalized_error,
        )

    @property
    def cycle_count(self) -> int:
        """実行した取引サイクル数を返す。"""

        return len(self.cycles)

    @property
    def completed_cycle_count(self) -> int:
        """正常完了した取引サイクル数を返す。"""

        return sum(
            cycle.is_completed
            for cycle in self.cycles
        )

    @property
    def failed_cycle_count(self) -> int:
        """失敗した取引サイクル数を返す。"""

        return sum(
            cycle.is_failed
            for cycle in self.cycles
        )

    @property
    def signal_count(self) -> int:
        """生成されたシグナル総数を返す。"""

        return sum(
            cycle.signal_count
            for cycle in self.cycles
        )

    @property
    def execution_count(self) -> int:
        """約定総数を返す。"""

        return sum(
            cycle.execution_count
            for cycle in self.cycles
        )

    @property
    def was_stopped_by_error(self) -> bool:
        """エラーにより終了したか返す。"""

        return (
            self.stop_reason
            is MarketSchedulerStopReason.ERROR
        )