"""リアルタイム市場監視とPaper Tradingを継続実行する。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from time import sleep
from typing import Protocol

from app.live.live_orchestrator_models import (
    LiveCycleResult,
    LiveCycleStatus,
    LiveRunResult,
    LiveRunStopReason,
)
from app.market.realtime_models import (
    RealtimeMarketPollResult,
    RealtimePollDecision,
)
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingResult,
)


class LiveMarketMonitor(Protocol):
    """リアルタイム市場監視処理。"""

    def poll(
        self,
        *,
        codes: Iterable[str],
        observed_at: datetime,
    ) -> RealtimeMarketPollResult:
        """市場監視を1サイクル実行する。"""


class LivePaperTradingService(Protocol):
    """リアルタイムPaper Trading処理。"""

    def process(
        self,
        prices,
        *,
        continue_on_error: bool = False,
    ) -> RealtimePaperTradingResult:
        """新規足をPaper Tradingへ流す。"""


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


class LiveTradingOrchestrator:
    """市場監視とPaper Tradingを一定間隔で継続実行する。"""

    def __init__(
        self,
        *,
        market_monitor: LiveMarketMonitor,
        paper_trading_service: LivePaperTradingService,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
    ) -> None:
        """依存関係と実行制御処理を設定する。"""

        self.market_monitor = market_monitor
        self.paper_trading_service = paper_trading_service
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

    def run(
        self,
        *,
        codes: Iterable[str],
        poll_interval_seconds: float = 30.0,
        max_cycles: int | None = None,
        continue_on_error: bool = True,
    ) -> LiveRunResult:
        """停止条件成立までリアルタイム処理を繰り返す。"""

        if poll_interval_seconds < 0:
            raise ValueError(
                "ポーリング間隔は0秒以上である必要があります。"
            )

        if max_cycles is not None and max_cycles <= 0:
            raise ValueError(
                "最大サイクル数は0より大きい必要があります。"
            )

        normalized_codes = tuple(codes)

        if not normalized_codes:
            raise ValueError(
                "監視対象銘柄を1件以上指定してください。"
            )

        started_at = self._current_time()
        cycles: list[LiveCycleResult] = []
        stop_reason = LiveRunStopReason.STOP_REQUESTED

        while True:
            if self.stop_requested():
                stop_reason = LiveRunStopReason.STOP_REQUESTED
                break

            if (
                max_cycles is not None
                and len(cycles) >= max_cycles
            ):
                stop_reason = (
                    LiveRunStopReason.MAX_CYCLES_REACHED
                )
                break

            cycle_number = len(cycles) + 1

            try:
                cycle = self.run_cycle(
                    cycle_number=cycle_number,
                    codes=normalized_codes,
                    continue_on_error=continue_on_error,
                )
            except Exception:
                if continue_on_error:
                    raise

                stop_reason = LiveRunStopReason.ERROR
                raise

            cycles.append(cycle)

            if cycle.is_failed and not continue_on_error:
                stop_reason = LiveRunStopReason.ERROR
                break

            if (
                max_cycles is not None
                and len(cycles) >= max_cycles
            ):
                stop_reason = (
                    LiveRunStopReason.MAX_CYCLES_REACHED
                )
                break

            if self.stop_requested():
                stop_reason = LiveRunStopReason.STOP_REQUESTED
                break

            self.sleeper(poll_interval_seconds)

        return LiveRunResult(
            started_at=started_at,
            completed_at=self._current_time(),
            stop_reason=stop_reason,
            cycles=tuple(cycles),
        )

    def run_cycle(
        self,
        *,
        cycle_number: int,
        codes: Iterable[str],
        continue_on_error: bool = True,
    ) -> LiveCycleResult:
        """市場監視とPaper Tradingを1回だけ実行する。"""

        started_at = self._current_time()

        try:
            market_result = self.market_monitor.poll(
                codes=codes,
                observed_at=started_at,
            )
            paper_result = None

            if (
                market_result.decision
                is RealtimePollDecision.NEW_BARS_SAVED
            ):
                paper_result = (
                    self.paper_trading_service.process(
                        market_result.new_bars,
                        continue_on_error=continue_on_error,
                    )
                )

            return LiveCycleResult(
                cycle_number=cycle_number,
                started_at=started_at,
                completed_at=self._current_time(),
                status=LiveCycleStatus.COMPLETED,
                market_result=market_result,
                paper_trading_result=paper_result,
                error_message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return LiveCycleResult(
                cycle_number=cycle_number,
                started_at=started_at,
                completed_at=self._current_time(),
                status=LiveCycleStatus.FAILED,
                market_result=None,
                paper_trading_result=None,
                error_message=str(error),
            )

    def _current_time(self) -> datetime:
        """タイムゾーン付き現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current
