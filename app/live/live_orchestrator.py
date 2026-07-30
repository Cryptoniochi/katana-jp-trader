"""リアルタイム市場監視とPaper Tradingを継続実行する。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class LiveMarketDataDiagnosticSnapshot:
    """市場データからPaper Tradingまでの経路診断。"""

    cycle_count: int
    decision_counts: dict[str, int]
    fetched_bar_count: int
    new_bar_count: int
    saved_bar_count: int
    paper_trading_call_count: int
    paper_trading_input_bar_count: int
    signal_processed_bar_count: int
    signal_skipped_duplicate_count: int
    signal_count: int

    @property
    def new_bars_saved_cycle_count(self) -> int:
        return self.decision_counts.get(
            RealtimePollDecision.NEW_BARS_SAVED.value, 0
        )

    @property
    def no_new_bar_cycle_count(self) -> int:
        return self.decision_counts.get(
            RealtimePollDecision.NO_NEW_BAR.value, 0
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
        self._diagnostic_cycle_count = 0
        self._diagnostic_decisions: Counter[str] = Counter()
        self._diagnostic_fetched_bar_count = 0
        self._diagnostic_new_bar_count = 0
        self._diagnostic_saved_bar_count = 0
        self._diagnostic_paper_call_count = 0
        self._diagnostic_paper_input_bar_count = 0
        self._diagnostic_signal_processed_bar_count = 0
        self._diagnostic_signal_skipped_duplicate_count = 0
        self._diagnostic_signal_count = 0

    def diagnostic_snapshot(
        self,
    ) -> LiveMarketDataDiagnosticSnapshot:
        """現在までの市場データ経路診断を返す。"""

        return LiveMarketDataDiagnosticSnapshot(
            cycle_count=self._diagnostic_cycle_count,
            decision_counts=dict(self._diagnostic_decisions),
            fetched_bar_count=self._diagnostic_fetched_bar_count,
            new_bar_count=self._diagnostic_new_bar_count,
            saved_bar_count=self._diagnostic_saved_bar_count,
            paper_trading_call_count=self._diagnostic_paper_call_count,
            paper_trading_input_bar_count=(
                self._diagnostic_paper_input_bar_count
            ),
            signal_processed_bar_count=(
                self._diagnostic_signal_processed_bar_count
            ),
            signal_skipped_duplicate_count=(
                self._diagnostic_signal_skipped_duplicate_count
            ),
            signal_count=self._diagnostic_signal_count,
        )

    def reset_diagnostics(self) -> None:
        """市場データ経路診断を初期化する。"""

        self._diagnostic_cycle_count = 0
        self._diagnostic_decisions.clear()
        self._diagnostic_fetched_bar_count = 0
        self._diagnostic_new_bar_count = 0
        self._diagnostic_saved_bar_count = 0
        self._diagnostic_paper_call_count = 0
        self._diagnostic_paper_input_bar_count = 0
        self._diagnostic_signal_processed_bar_count = 0
        self._diagnostic_signal_skipped_duplicate_count = 0
        self._diagnostic_signal_count = 0

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
            self._record_market_result(market_result)
            paper_result = None

            if (
                market_result.decision
                is RealtimePollDecision.NEW_BARS_SAVED
            ):
                self._diagnostic_paper_call_count += 1
                self._diagnostic_paper_input_bar_count += len(
                    market_result.new_bars
                )
                paper_result = (
                    self.paper_trading_service.process(
                        market_result.new_bars,
                        continue_on_error=continue_on_error,
                    )
                )
                self._record_paper_result(paper_result)

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

    def _record_market_result(
        self,
        result: RealtimeMarketPollResult,
    ) -> None:
        self._diagnostic_cycle_count += 1
        self._diagnostic_decisions[result.decision.value] += 1
        self._diagnostic_fetched_bar_count += result.fetched_bar_count
        self._diagnostic_new_bar_count += result.new_bar_count
        self._diagnostic_saved_bar_count += result.saved_bar_count

    def _record_paper_result(
        self,
        result: RealtimePaperTradingResult,
    ) -> None:
        signal_result = result.signal_result
        if signal_result is None:
            return

        self._diagnostic_signal_processed_bar_count += (
            signal_result.processed_bar_count
        )
        self._diagnostic_signal_skipped_duplicate_count += (
            signal_result.skipped_duplicate_count
        )
        self._diagnostic_signal_count += signal_result.signal_count

    def _current_time(self) -> datetime:
        """タイムゾーン付き現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current
