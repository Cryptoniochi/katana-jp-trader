"""Trading Loopを長時間連続実行して耐久統計を収集する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from time import sleep
from typing import Protocol

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.runtime.burn_in_models import (
    BurnInCycleSample,
    BurnInResult,
    BurnInSettings,
    BurnInStopReason,
)


class BurnInCycleRunner(Protocol):
    """Burn-in Runnerが利用するTrading Loop。"""

    def run_cycle(self):
        """Trading Cycleを1回実行する。"""


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


class BurnInRunner:
    """耐久試験設定に従ってTrading Cycleを繰り返す。"""

    def __init__(
        self,
        *,
        component: BurnInCycleRunner,
        settings: BurnInSettings | None = None,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
    ) -> None:
        """Component・設定・時計・停止判定を設定する。"""

        self.component = component
        self.settings = (
            settings
            if settings is not None
            else BurnInSettings()
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

    def run(self) -> BurnInResult:
        """終了条件成立まで耐久試験を実行する。"""

        started_at = self._current_time()
        samples: list[BurnInCycleSample] = []
        consecutive_failures = 0
        stop_reason = BurnInStopReason.STOP_REQUESTED
        error_message: str | None = None

        while True:
            current = self._current_time()

            if self.stop_requested():
                stop_reason = BurnInStopReason.STOP_REQUESTED
                break

            if (
                self.settings.maximum_cycles is not None
                and len(samples) >= self.settings.maximum_cycles
            ):
                stop_reason = (
                    BurnInStopReason.MAX_CYCLES_REACHED
                )
                break

            if (
                self.settings.maximum_duration_seconds is not None
                and (
                    current - started_at
                ).total_seconds()
                >= self.settings.maximum_duration_seconds
            ):
                stop_reason = (
                    BurnInStopReason.MAX_DURATION_REACHED
                )
                break

            cycle_started_at = current

            try:
                cycle_result = self.component.run_cycle()
            except Exception as error:
                stop_reason = BurnInStopReason.ERROR
                error_message = (
                    str(error).strip()
                    or type(error).__name__
                )
                break

            cycle_completed_at = self._current_time()
            duration_seconds = max(
                0.0,
                (
                    cycle_completed_at - cycle_started_at
                ).total_seconds(),
            )

            if cycle_result.is_successful:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            samples.append(
                BurnInCycleSample(
                    cycle_result=cycle_result,
                    duration_seconds=duration_seconds,
                    consecutive_failure_count=(
                        consecutive_failures
                    ),
                )
            )

            if (
                cycle_result.status
                is TradingLoopCycleStatus.RESOURCE_CRITICAL
                and self.settings.stop_on_resource_critical
            ):
                stop_reason = (
                    BurnInStopReason.RESOURCE_CRITICAL
                )
                break

            if (
                not cycle_result.is_successful
                and not self.settings.continue_on_cycle_failure
            ):
                stop_reason = (
                    BurnInStopReason.CONSECUTIVE_FAILURE_LIMIT
                )
                break

            if (
                consecutive_failures
                >= self.settings.maximum_consecutive_failures
            ):
                stop_reason = (
                    BurnInStopReason.CONSECUTIVE_FAILURE_LIMIT
                )
                break

            if (
                self.settings.maximum_cycles is not None
                and len(samples) >= self.settings.maximum_cycles
            ):
                stop_reason = (
                    BurnInStopReason.MAX_CYCLES_REACHED
                )
                break

            if (
                self.settings.maximum_duration_seconds is not None
                and (
                    cycle_completed_at - started_at
                ).total_seconds()
                >= self.settings.maximum_duration_seconds
            ):
                stop_reason = (
                    BurnInStopReason.MAX_DURATION_REACHED
                )
                break

            if self.stop_requested():
                stop_reason = BurnInStopReason.STOP_REQUESTED
                break

            self.sleeper(
                self.settings.cycle_interval_seconds
            )

        return BurnInResult(
            started_at=started_at,
            completed_at=self._current_time(),
            stop_reason=stop_reason,
            samples=tuple(samples),
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
