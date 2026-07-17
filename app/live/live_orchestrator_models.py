"""リアルタイム運転オーケストレーターの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.market.realtime_models import (
    RealtimeMarketPollResult,
)
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingResult,
)


class LiveCycleStatus(StrEnum):
    """1サイクルの終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


class LiveRunStopReason(StrEnum):
    """継続運転の終了理由。"""

    STOP_REQUESTED = "stop_requested"
    MAX_CYCLES_REACHED = "max_cycles_reached"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LiveCycleResult:
    """リアルタイム運転1サイクルの結果。"""

    cycle_number: int
    started_at: datetime
    completed_at: datetime
    status: LiveCycleStatus
    market_result: RealtimeMarketPollResult | None
    paper_trading_result: RealtimePaperTradingResult | None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """件数・日時・状態の整合性を検証する。"""

        if self.cycle_number <= 0:
            raise ValueError(
                "サイクル番号は0より大きい必要があります。"
            )

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

        if self.status is LiveCycleStatus.COMPLETED:
            if self.market_result is None:
                raise ValueError(
                    "完了結果には市場監視結果が必要です。"
                )

            if self.error_message is not None:
                raise ValueError(
                    "完了結果にはエラーメッセージを"
                    "設定できません。"
                )

        if self.status is LiveCycleStatus.FAILED:
            if not (self.error_message or "").strip():
                raise ValueError(
                    "失敗結果にはエラーメッセージが必要です。"
                )

    @property
    def signal_count(self) -> int:
        """生成シグナル件数を返す。"""

        if self.paper_trading_result is None:
            return 0

        return self.paper_trading_result.signal_count

    @property
    def execution_count(self) -> int:
        """約定件数を返す。"""

        if self.paper_trading_result is None:
            return 0

        return self.paper_trading_result.execution_count

    @property
    def is_completed(self) -> bool:
        """正常完了したか返す。"""

        return self.status is LiveCycleStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """失敗したか返す。"""

        return self.status is LiveCycleStatus.FAILED


@dataclass(frozen=True, slots=True)
class LiveRunResult:
    """リアルタイム継続運転の全体結果。"""

    started_at: datetime
    completed_at: datetime
    stop_reason: LiveRunStopReason
    cycles: tuple[LiveCycleResult, ...]

    def __post_init__(self) -> None:
        """日時とサイクル順序を検証する。"""

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

        expected_numbers = list(
            range(1, len(self.cycles) + 1)
        )
        actual_numbers = [
            cycle.cycle_number
            for cycle in self.cycles
        ]

        if actual_numbers != expected_numbers:
            raise ValueError(
                "サイクル番号は1からの連番である必要があります。"
            )

    @property
    def cycle_count(self) -> int:
        """総サイクル数を返す。"""

        return len(self.cycles)

    @property
    def completed_cycle_count(self) -> int:
        """正常完了サイクル数を返す。"""

        return sum(
            cycle.is_completed
            for cycle in self.cycles
        )

    @property
    def failed_cycle_count(self) -> int:
        """失敗サイクル数を返す。"""

        return sum(
            cycle.is_failed
            for cycle in self.cycles
        )

    @property
    def signal_count(self) -> int:
        """全サイクルのシグナル件数を返す。"""

        return sum(
            cycle.signal_count
            for cycle in self.cycles
        )

    @property
    def execution_count(self) -> int:
        """全サイクルの約定件数を返す。"""

        return sum(
            cycle.execution_count
            for cycle in self.cycles
        )
