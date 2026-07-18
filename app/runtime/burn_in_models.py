"""長時間耐久運転の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.trading_loop_models import (
    TradingLoopCycleResult,
)


class BurnInStopReason(StrEnum):
    """耐久試験の終了理由。"""

    MAX_CYCLES_REACHED = "max_cycles_reached"
    MAX_DURATION_REACHED = "max_duration_reached"
    STOP_REQUESTED = "stop_requested"
    CONSECUTIVE_FAILURE_LIMIT = "consecutive_failure_limit"
    RESOURCE_CRITICAL = "resource_critical"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class BurnInSettings:
    """耐久試験の実行設定。"""

    maximum_cycles: int | None = 10_000
    maximum_duration_seconds: float | None = None
    cycle_interval_seconds: float = 0.0
    maximum_consecutive_failures: int = 5
    stop_on_resource_critical: bool = True
    continue_on_cycle_failure: bool = True

    def __post_init__(self) -> None:
        """設定値を検証する。"""

        if (
            self.maximum_cycles is None
            and self.maximum_duration_seconds is None
        ):
            raise ValueError(
                "最大サイクル数または最大実行時間を指定してください。"
            )

        if (
            self.maximum_cycles is not None
            and self.maximum_cycles <= 0
        ):
            raise ValueError(
                "最大サイクル数は0より大きい必要があります。"
            )

        if (
            self.maximum_duration_seconds is not None
            and self.maximum_duration_seconds <= 0
        ):
            raise ValueError(
                "最大実行時間は0より大きい必要があります。"
            )

        if self.cycle_interval_seconds < 0:
            raise ValueError(
                "サイクル間隔は0秒以上である必要があります。"
            )

        if self.maximum_consecutive_failures <= 0:
            raise ValueError(
                "最大連続失敗数は0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class BurnInCycleSample:
    """耐久試験中の1サイクル計測値。"""

    cycle_result: TradingLoopCycleResult
    duration_seconds: float
    consecutive_failure_count: int

    def __post_init__(self) -> None:
        """計測値を検証する。"""

        if self.duration_seconds < 0:
            raise ValueError(
                "サイクル時間は0秒以上である必要があります。"
            )

        if self.consecutive_failure_count < 0:
            raise ValueError(
                "連続失敗数は0以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class BurnInResult:
    """耐久試験の最終結果。"""

    started_at: datetime
    completed_at: datetime
    stop_reason: BurnInStopReason
    samples: tuple[BurnInCycleSample, ...]
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
            range(1, len(self.samples) + 1)
        )
        actual = [
            sample.cycle_result.cycle_number
            for sample in self.samples
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
            self.stop_reason is BurnInStopReason.ERROR
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
    def elapsed_seconds(self) -> float:
        """試験全体の経過時間を返す。"""

        return (
            self.completed_at - self.started_at
        ).total_seconds()

    @property
    def cycle_count(self) -> int:
        """総サイクル数を返す。"""

        return len(self.samples)

    @property
    def successful_cycle_count(self) -> int:
        """正常完了サイクル数を返す。"""

        return sum(
            sample.cycle_result.is_successful
            for sample in self.samples
        )

    @property
    def failed_cycle_count(self) -> int:
        """正常完了以外のサイクル数を返す。"""

        return (
            self.cycle_count
            - self.successful_cycle_count
        )

    @property
    def average_cycle_seconds(self) -> float:
        """平均サイクル時間を返す。"""

        if not self.samples:
            return 0.0

        return sum(
            sample.duration_seconds
            for sample in self.samples
        ) / len(self.samples)

    @property
    def minimum_cycle_seconds(self) -> float:
        """最短サイクル時間を返す。"""

        if not self.samples:
            return 0.0

        return min(
            sample.duration_seconds
            for sample in self.samples
        )

    @property
    def maximum_cycle_seconds(self) -> float:
        """最長サイクル時間を返す。"""

        if not self.samples:
            return 0.0

        return max(
            sample.duration_seconds
            for sample in self.samples
        )

    @property
    def maximum_consecutive_failures(self) -> int:
        """試験中の最大連続失敗数を返す。"""

        if not self.samples:
            return 0

        return max(
            sample.consecutive_failure_count
            for sample in self.samples
        )
