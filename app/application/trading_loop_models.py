"""Application Trading Loopの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_orchestrator_models import LiveCycleResult
from app.runtime.resource_integration import (
    RuntimeResourceIntegrationResult,
)
from app.runtime.session_models import RuntimeSessionSnapshot


class TradingLoopCycleStatus(StrEnum):
    """Application Trading Loopの1サイクル状態。"""

    COMPLETED = "completed"
    RESOURCE_CRITICAL = "resource_critical"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TradingLoopCycleResult:
    """市場監視からRuntime記録までをまとめた1サイクル結果。"""

    cycle_number: int
    started_at: datetime
    completed_at: datetime
    status: TradingLoopCycleStatus
    live_cycle_result: LiveCycleResult | None
    runtime_session_snapshot: RuntimeSessionSnapshot
    resource_result: RuntimeResourceIntegrationResult | None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """日時・状態・結果の整合性を検証する。"""

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

        error_message = (
            None
            if self.error_message is None
            else self.error_message.strip() or None
        )

        if self.status is TradingLoopCycleStatus.COMPLETED:
            if self.live_cycle_result is None:
                raise ValueError(
                    "正常完了にはLive Cycle結果が必要です。"
                )
            if not self.live_cycle_result.is_completed:
                raise ValueError(
                    "正常完了には成功したLive Cycle結果が必要です。"
                )
            if error_message is not None:
                raise ValueError(
                    "正常完了にはエラーメッセージを設定できません。"
                )

        if self.status is TradingLoopCycleStatus.RESOURCE_CRITICAL:
            if self.resource_result is None:
                raise ValueError(
                    "Resource重大状態にはResource結果が必要です。"
                )
            if error_message is not None:
                raise ValueError(
                    "Resource重大状態にはエラーメッセージを"
                    "設定できません。"
                )

        if self.status is TradingLoopCycleStatus.FAILED:
            if error_message is None:
                raise ValueError(
                    "失敗結果にはエラーメッセージが必要です。"
                )

        object.__setattr__(
            self,
            "error_message",
            error_message,
        )

    @property
    def is_successful(self) -> bool:
        """サイクルが正常完了したか返す。"""

        return self.status is TradingLoopCycleStatus.COMPLETED

    @property
    def signal_count(self) -> int:
        """生成シグナル件数を返す。"""

        if self.live_cycle_result is None:
            return 0

        return self.live_cycle_result.signal_count

    @property
    def execution_count(self) -> int:
        """約定件数を返す。"""

        if self.live_cycle_result is None:
            return 0

        return self.live_cycle_result.execution_count


@dataclass(frozen=True, slots=True)
class TradingLoopRunResult:
    """複数Trading Cycleの集約結果。"""

    cycles: tuple[TradingLoopCycleResult, ...]

    def __post_init__(self) -> None:
        """サイクル番号が1からの連番か検証する。"""

        actual = [
            item.cycle_number
            for item in self.cycles
        ]
        expected = list(
            range(1, len(self.cycles) + 1)
        )

        if actual != expected:
            raise ValueError(
                "サイクル番号は1からの連番である必要があります。"
            )

    @property
    def cycle_count(self) -> int:
        """総サイクル数を返す。"""

        return len(self.cycles)

    @property
    def successful_cycle_count(self) -> int:
        """正常完了サイクル数を返す。"""

        return sum(
            item.is_successful
            for item in self.cycles
        )

    @property
    def failed_cycle_count(self) -> int:
        """正常完了以外のサイクル数を返す。"""

        return self.cycle_count - self.successful_cycle_count

    @property
    def signal_count(self) -> int:
        """生成シグナル件数合計を返す。"""

        return sum(
            item.signal_count
            for item in self.cycles
        )

    @property
    def execution_count(self) -> int:
        """約定件数合計を返す。"""

        return sum(
            item.execution_count
            for item in self.cycles
        )
