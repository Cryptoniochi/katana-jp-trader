"""Market-aware運転・永続化・Dashboard更新・後処理を統合する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from time import sleep
from typing import Protocol

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.market.market_clock import (
    TokyoMarketClock,
)
from app.market.market_session import (
    TokyoMarketSession,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDaySettings,
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_persistence_service import (
    PaperTradingPersistenceResult,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
)


class PaperTradingDayRuntime(Protocol):
    """終日運用Serviceが利用するPaper Trading Runtime。"""

    def start(self) -> None:
        """Runtimeを開始する。"""

    def run_cycle(self):
        """Trading Cycleを実行する。"""

    def complete(self) -> PaperTradingDailySummary:
        """正常終了の日次Summaryを返す。"""

    def fail(
        self,
        *,
        error_message: str,
    ) -> PaperTradingDailySummary:
        """異常終了の日次Summaryを返す。"""


class PaperTradingDayPersister(Protocol):
    """終日運用Serviceが利用する永続化処理。"""

    def persist(
        self,
        summary: PaperTradingDailySummary,
    ) -> PaperTradingPersistenceResult:
        """日次Summaryを保存する。"""


class PaperTradingDayDashboardPublisher(Protocol):
    """終日運用後にDashboard Snapshotを公開する。"""

    def publish(self):
        """現在のDashboard Snapshotを生成して保存する。"""


class PaperTradingDayPostRunHook(Protocol):
    """終日運用結果を受け取る任意後処理。"""

    def handle(
        self,
        result: PaperTradingDayResult,
    ) -> None:
        """運用結果を使って後処理する。"""


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


class PaperTradingDayService:
    """市場時間に従って1営業日のPaper Tradingを実行する。"""

    def __init__(
        self,
        *,
        runtime: PaperTradingDayRuntime,
        persistence_service: PaperTradingDayPersister,
        market_clock: TokyoMarketClock,
        dashboard_publisher: (
            PaperTradingDayDashboardPublisher | None
        ) = None,
        post_run_hooks: tuple[
            PaperTradingDayPostRunHook,
            ...,
        ] = (),
        settings: PaperTradingDaySettings | None = None,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
    ) -> None:
        """依存関係・運用設定・時計を設定する。"""

        self.runtime = runtime
        self.persistence_service = persistence_service
        self.market_clock = market_clock
        self.dashboard_publisher = dashboard_publisher
        self.post_run_hooks = tuple(post_run_hooks)
        self.settings = (
            settings
            if settings is not None
            else PaperTradingDaySettings()
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

    def run(self) -> PaperTradingDayResult:
        """市場終了または停止条件まで終日運用する。"""

        started_at = self._current_time()
        self.runtime.start()
        cycle_count = 0
        stop_reason = PaperTradingDayStopReason.MARKET_CLOSED
        error_message: str | None = None

        try:
            while True:
                if self.stop_requested():
                    stop_reason = (
                        PaperTradingDayStopReason.STOP_REQUESTED
                    )
                    break

                if (
                    self.settings.maximum_cycles is not None
                    and cycle_count >= self.settings.maximum_cycles
                ):
                    stop_reason = (
                        PaperTradingDayStopReason
                        .MAX_CYCLES_REACHED
                    )
                    break

                clock_snapshot = self.market_clock.snapshot(
                    self._current_time()
                )

                if (
                    clock_snapshot.session
                    is TokyoMarketSession.AFTER_CLOSE
                ):
                    stop_reason = (
                        PaperTradingDayStopReason.MARKET_CLOSED
                    )
                    break

                if not clock_snapshot.is_open:
                    self._sleep_closed_market(
                        clock_snapshot.wait_seconds
                    )
                    continue

                cycle_record = self.runtime.run_cycle()
                cycle_count += 1
                cycle_result = cycle_record.cycle_result

                if (
                    cycle_result.status
                    is TradingLoopCycleStatus.RESOURCE_CRITICAL
                    and self.settings.stop_on_resource_critical
                ):
                    stop_reason = (
                        PaperTradingDayStopReason
                        .RESOURCE_CRITICAL
                    )
                    break

                if (
                    cycle_result.status
                    is TradingLoopCycleStatus.FAILED
                    and self.settings.stop_on_cycle_failure
                ):
                    stop_reason = (
                        PaperTradingDayStopReason.CYCLE_FAILED
                    )
                    break

                if (
                    self.settings.maximum_cycles is not None
                    and cycle_count >= self.settings.maximum_cycles
                ):
                    stop_reason = (
                        PaperTradingDayStopReason
                        .MAX_CYCLES_REACHED
                    )
                    break

                if self.stop_requested():
                    stop_reason = (
                        PaperTradingDayStopReason.STOP_REQUESTED
                    )
                    break

                self.sleeper(
                    self.settings.cycle_interval_seconds
                )

            summary = self.runtime.complete()

        except Exception as error:
            stop_reason = PaperTradingDayStopReason.ERROR
            error_message = (
                str(error).strip()
                or type(error).__name__
            )
            summary = self.runtime.fail(
                error_message=error_message
            )

        persistence = self.persistence_service.persist(
            summary
        )
        (
            dashboard_published,
            dashboard_error_message,
        ) = self._publish_dashboard()
        completed_at = self._current_time()

        result = PaperTradingDayResult(
            trading_date=summary.trading_date,
            started_at=started_at,
            completed_at=completed_at,
            stop_reason=stop_reason,
            summary=summary,
            record=persistence.record,
            error_message=error_message,
            dashboard_published=dashboard_published,
            dashboard_error_message=dashboard_error_message,
        )

        return self._run_post_run_hooks(result)

    def _run_post_run_hooks(
        self,
        result: PaperTradingDayResult,
    ) -> PaperTradingDayResult:
        """後処理Hookを順番に実行して結果へ反映する。"""

        completed_count = 0
        error_messages: list[str] = []

        for hook in self.post_run_hooks:
            try:
                hook.handle(result)
                completed_count += 1
            except Exception as error:
                if not self.settings.continue_on_post_run_hook_error:
                    raise

                error_messages.append(
                    str(error).strip()
                    or type(error).__name__
                )

        return replace(
            result,
            completed_post_run_hook_count=completed_count,
            post_run_hook_error_messages=tuple(
                error_messages
            ),
        )

    def _publish_dashboard(
        self,
    ) -> tuple[bool, str | None]:
        """日次保存後にDashboard Snapshotを公開する。"""

        if self.dashboard_publisher is None:
            return False, None

        try:
            self.dashboard_publisher.publish()
        except Exception as error:
            if not self.settings.continue_on_dashboard_error:
                raise

            return (
                False,
                str(error).strip()
                or type(error).__name__,
            )

        return True, None

    def _sleep_closed_market(
        self,
        wait_seconds: float,
    ) -> None:
        """市場再確認までの待機時間を最大5分へ制限する。"""

        self.sleeper(
            max(
                1.0,
                min(wait_seconds, 300.0),
            )
        )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
