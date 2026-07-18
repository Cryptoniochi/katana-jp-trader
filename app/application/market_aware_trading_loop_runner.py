"""Market Clockに従ってTrading Loop Runnerを制御する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from time import sleep
from typing import Protocol

from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
    TradingLoopRunnerStopReason,
)
from app.market.market_clock import (
    TokyoMarketClock,
    TokyoMarketClockSnapshot,
)


class ScheduledTradingLoopComponent(Protocol):
    """Market-aware Runnerが利用するTrading Loop。"""

    def run_cycle(self):
        """Trading Cycleを1回実行する。"""


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


class MarketAwareTradingLoopRunner:
    """東京市場の営業状態に従ってTrading Cycleを実行する。"""

    def __init__(
        self,
        *,
        component: ScheduledTradingLoopComponent,
        market_clock: TokyoMarketClock,
        cycle_interval_seconds: float = 30.0,
        maximum_cycles: int | None = None,
        stop_after_market_close: bool = False,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
    ) -> None:
        """Component・市場時計・実行制御を設定する。"""

        if cycle_interval_seconds < 0:
            raise ValueError(
                "サイクル間隔は0秒以上である必要があります。"
            )

        if maximum_cycles is not None and maximum_cycles <= 0:
            raise ValueError(
                "最大サイクル数は0より大きい必要があります。"
            )

        self.component = component
        self.market_clock = market_clock
        self.cycle_interval_seconds = cycle_interval_seconds
        self.maximum_cycles = maximum_cycles
        self.stop_after_market_close = stop_after_market_close
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
        """停止条件成立までMarket Clockに従って実行する。"""

        started_at = self._current_time()
        cycles = []
        error_message: str | None = None
        stop_reason = TradingLoopRunnerStopReason.STOP_REQUESTED

        while True:
            if self.stop_requested():
                stop_reason = (
                    TradingLoopRunnerStopReason.STOP_REQUESTED
                )
                break

            if (
                self.maximum_cycles is not None
                and len(cycles) >= self.maximum_cycles
            ):
                stop_reason = (
                    TradingLoopRunnerStopReason.MAX_CYCLES_REACHED
                )
                break

            clock_snapshot = self.market_clock.snapshot(
                self._current_time()
            )

            if not clock_snapshot.is_open:
                if (
                    self.stop_after_market_close
                    and clock_snapshot.session.value
                    == "after_close"
                ):
                    stop_reason = (
                        TradingLoopRunnerStopReason.STOP_REQUESTED
                    )
                    break

                self._sleep_until_next_check(
                    clock_snapshot
                )
                continue

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
                self.maximum_cycles is not None
                and len(cycles) >= self.maximum_cycles
            ):
                stop_reason = (
                    TradingLoopRunnerStopReason.MAX_CYCLES_REACHED
                )
                break

            if self.stop_requested():
                stop_reason = (
                    TradingLoopRunnerStopReason.STOP_REQUESTED
                )
                break

            self.sleeper(self.cycle_interval_seconds)

        return TradingLoopRunnerResult(
            started_at=started_at,
            completed_at=self._current_time(),
            stop_reason=stop_reason,
            cycles=tuple(cycles),
            error_message=error_message,
        )

    def _sleep_until_next_check(
        self,
        snapshot: TokyoMarketClockSnapshot,
    ) -> None:
        """市場再開までの待機時間を適切な長さへ制限する。"""

        wait_seconds = max(
            1.0,
            min(
                snapshot.wait_seconds,
                300.0,
            ),
        )
        self.sleeper(wait_seconds)

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
