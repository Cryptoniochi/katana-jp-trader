"""TradingLoopComponentを一定間隔で繰り返し実行する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from time import sleep
from typing import Protocol

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
    TradingLoopRunnerSettings,
    TradingLoopRunnerStopReason,
)


class TradingLoopCycleRunner(Protocol):
    """Runnerが利用するTrading Loop Component。"""

    def run_cycle(self):
        """次のTrading Cycleを実行する。"""


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


class TradingLoopRunner:
    """停止条件成立までTrading Cycleを繰り返す。"""

    def __init__(
        self,
        *,
        component: TradingLoopCycleRunner,
        settings: TradingLoopRunnerSettings | None = None,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
    ) -> None:
        """Component・設定・時計・停止判定を設定する。"""

        self.component = component
        self.settings = (
            settings
            if settings is not None
            else TradingLoopRunnerSettings()
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.sleeper = sleeper
        self.stop_requested = (
            stop_requested
            if stop_requested is not None
            else lambda: False
        )

    def run(self) -> TradingLoopRunnerResult:
        """停止条件成立までTrading Cycleを繰り返す。"""

        started_at = self._current_time()
        cycles = []
        stop_reason = (
            TradingLoopRunnerStopReason.STOP_REQUESTED
        )
        error_message: str | None = None

        while True:
            if self.stop_requested():
                stop_reason = (
                    TradingLoopRunnerStopReason.STOP_REQUESTED
                )
                break

            if (
                self.settings.maximum_cycles is not None
                and len(cycles)
                >= self.settings.maximum_cycles
            ):
                stop_reason = (
                    TradingLoopRunnerStopReason
                    .MAX_CYCLES_REACHED
                )
                break

            try:
                cycle = self.component.run_cycle()
            except Exception as error:
                stop_reason = TradingLoopRunnerStopReason.ERROR
                error_message = (
                    str(error).strip()
                    or type(error).__name__
                )
                break

            cycles.append(cycle)

            if (
                cycle.status
                is TradingLoopCycleStatus.RESOURCE_CRITICAL
                and self.settings.stop_on_resource_critical
            ):
                stop_reason = (
                    TradingLoopRunnerStopReason
                    .RESOURCE_CRITICAL
                )
                break

            if (
                cycle.status is TradingLoopCycleStatus.FAILED
                and self.settings.stop_on_cycle_failure
            ):
                stop_reason = (
                    TradingLoopRunnerStopReason
                    .CYCLE_FAILED
                )
                break

            if (
                self.settings.maximum_cycles is not None
                and len(cycles)
                >= self.settings.maximum_cycles
            ):
                stop_reason = (
                    TradingLoopRunnerStopReason
                    .MAX_CYCLES_REACHED
                )
                break

            if self.stop_requested():
                stop_reason = (
                    TradingLoopRunnerStopReason.STOP_REQUESTED
                )
                break

            self.sleeper(
                self.settings.cycle_interval_seconds
            )

        return TradingLoopRunnerResult(
            started_at=started_at,
            completed_at=self._current_time(),
            stop_reason=stop_reason,
            cycles=tuple(cycles),
            error_message=error_message,
        )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
