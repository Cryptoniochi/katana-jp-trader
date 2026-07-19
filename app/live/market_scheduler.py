"""東京市場の日次運転を管理する市場スケジューラ。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, time, timedelta, timezone
from time import sleep
from typing import Protocol

from app.live.live_orchestrator_models import (
    LiveCycleResult,
)
from app.live.market_scheduler_models import (
    MarketSchedulerResult,
    MarketSchedulerSettings,
    MarketSchedulerStopReason,
)
from app.market.realtime_market_service import (
    JST,
    TokyoMarketSessionService,
)
from app.market.realtime_models import (
    MarketSessionSnapshot,
    MarketSessionState,
)


class ScheduledLiveOrchestrator(Protocol):
    """市場スケジューラが利用するOrchestrator。"""

    def run_cycle(
        self,
        *,
        cycle_number: int,
        codes: Iterable[str],
        continue_on_error: bool = True,
    ) -> LiveCycleResult:
        """リアルタイム処理を1サイクル実行する。"""


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


class MarketScheduler:
    """市場状態に応じてリアルタイム運転を開始・待機・終了する。"""

    def __init__(
        self,
        *,
        orchestrator: ScheduledLiveOrchestrator,
        session_service: TokyoMarketSessionService | None = None,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
    ) -> None:
        """Orchestrator、市場判定、時計を設定する。"""

        self.orchestrator = orchestrator
        self.session_service = (
            session_service
            if session_service is not None
            else TokyoMarketSessionService()
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

    def run(
        self,
        *,
        codes: Iterable[str],
        settings: MarketSchedulerSettings | None = None,
    ) -> MarketSchedulerResult:
        """当日の市場終了または停止条件成立まで運転する。"""

        resolved_settings = (
            settings
            if settings is not None
            else MarketSchedulerSettings()
        )
        normalized_codes = self._normalize_codes(codes)

        started_at = self._current_time()
        initial_session = (
            self.session_service.create_snapshot(
                started_at
            )
        )
        trading_date = initial_session.trading_date

        cycles: list[LiveCycleResult] = []
        sleep_count = 0
        slept_seconds = 0.0

        if not initial_session.is_trading_day:
            return self._create_result(
                started_at=started_at,
                trading_date=trading_date,
                stop_reason=(
                    MarketSchedulerStopReason.NON_TRADING_DAY
                ),
                cycles=cycles,
                sleep_count=sleep_count,
                slept_seconds=slept_seconds,
            )

        while True:
            if self.stop_requested():
                return self._create_result(
                    started_at=started_at,
                    trading_date=trading_date,
                    stop_reason=(
                        MarketSchedulerStopReason.STOP_REQUESTED
                    ),
                    cycles=cycles,
                    sleep_count=sleep_count,
                    slept_seconds=slept_seconds,
                )

            if (
                resolved_settings.max_cycles is not None
                and len(cycles)
                >= resolved_settings.max_cycles
            ):
                return self._create_result(
                    started_at=started_at,
                    trading_date=trading_date,
                    stop_reason=(
                        MarketSchedulerStopReason
                        .MAX_CYCLES_REACHED
                    ),
                    cycles=cycles,
                    sleep_count=sleep_count,
                    slept_seconds=slept_seconds,
                )

            observed_at = self._current_time()
            session = (
                self.session_service.create_snapshot(
                    observed_at
                )
            )

            if session.trading_date != trading_date:
                return self._create_result(
                    started_at=started_at,
                    trading_date=trading_date,
                    stop_reason=(
                        MarketSchedulerStopReason.MARKET_CLOSED
                    ),
                    cycles=cycles,
                    sleep_count=sleep_count,
                    slept_seconds=slept_seconds,
                )

            if not session.is_trading_day:
                return self._create_result(
                    started_at=started_at,
                    trading_date=trading_date,
                    stop_reason=(
                        MarketSchedulerStopReason.NON_TRADING_DAY
                    ),
                    cycles=cycles,
                    sleep_count=sleep_count,
                    slept_seconds=slept_seconds,
                )

            if (
                session.state
                is MarketSessionState.POST_CLOSE
            ):
                return self._create_result(
                    started_at=started_at,
                    trading_date=trading_date,
                    stop_reason=(
                        MarketSchedulerStopReason.MARKET_CLOSED
                    ),
                    cycles=cycles,
                    sleep_count=sleep_count,
                    slept_seconds=slept_seconds,
                )

            if session.is_trading:
                try:
                    cycle = self.orchestrator.run_cycle(
                        cycle_number=len(cycles) + 1,
                        codes=normalized_codes,
                        continue_on_error=(
                            resolved_settings.continue_on_error
                        ),
                    )
                except Exception as error:
                    return self._create_result(
                        started_at=started_at,
                        trading_date=trading_date,
                        stop_reason=(
                            MarketSchedulerStopReason.ERROR
                        ),
                        cycles=cycles,
                        sleep_count=sleep_count,
                        slept_seconds=slept_seconds,
                        error_message=(
                            str(error).strip()
                            or type(error).__name__
                        ),
                    )

                cycles.append(cycle)

                if (
                    cycle.is_failed
                    and not resolved_settings.continue_on_error
                ):
                    return self._create_result(
                        started_at=started_at,
                        trading_date=trading_date,
                        stop_reason=(
                            MarketSchedulerStopReason.ERROR
                        ),
                        cycles=cycles,
                        sleep_count=sleep_count,
                        slept_seconds=slept_seconds,
                        error_message=(
                            cycle.error_message
                            or "取引サイクルが失敗しました。"
                        ),
                    )

                if (
                    resolved_settings.max_cycles is not None
                    and len(cycles)
                    >= resolved_settings.max_cycles
                ):
                    return self._create_result(
                        started_at=started_at,
                        trading_date=trading_date,
                        stop_reason=(
                            MarketSchedulerStopReason
                            .MAX_CYCLES_REACHED
                        ),
                        cycles=cycles,
                        sleep_count=sleep_count,
                        slept_seconds=slept_seconds,
                    )

                wait_seconds = (
                    resolved_settings
                    .trading_poll_interval_seconds
                )
            else:
                wait_seconds = self._idle_wait_seconds(
                    session=session,
                    maximum_wait_seconds=(
                        resolved_settings
                        .idle_poll_interval_seconds
                    ),
                )

            if wait_seconds > 0:
                self.sleeper(wait_seconds)
                sleep_count += 1
                slept_seconds += wait_seconds

    def _create_result(
        self,
        *,
        started_at: datetime,
        trading_date,
        stop_reason: MarketSchedulerStopReason,
        cycles: list[LiveCycleResult],
        sleep_count: int,
        slept_seconds: float,
        error_message: str | None = None,
    ) -> MarketSchedulerResult:
        """現在の運転情報から終了結果を作成する。"""

        return MarketSchedulerResult(
            started_at=started_at,
            completed_at=self._current_time(),
            trading_date=trading_date,
            stop_reason=stop_reason,
            cycles=tuple(cycles),
            sleep_count=sleep_count,
            slept_seconds=slept_seconds,
            error_message=error_message,
        )

    @staticmethod
    def _idle_wait_seconds(
        *,
        session: MarketSessionSnapshot,
        maximum_wait_seconds: float,
    ) -> float:
        """次の市場セッションまでの待機秒数を返す。"""

        local_time = session.observed_at.astimezone(JST)

        if session.state is MarketSessionState.PRE_OPEN:
            transition_time = time(9, 0)
        elif (
            session.state
            is MarketSessionState.LUNCH_BREAK
        ):
            transition_time = time(12, 30)
        else:
            return maximum_wait_seconds

        transition_at = datetime.combine(
            local_time.date(),
            transition_time,
            tzinfo=JST,
        )

        remaining_seconds = (
            transition_at - local_time
        ).total_seconds()

        if remaining_seconds <= 0:
            return 0.0

        return min(
            maximum_wait_seconds,
            remaining_seconds,
        )

    def _current_time(self) -> datetime:
        """タイムゾーン付き現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current

    @staticmethod
    def _normalize_codes(
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """銘柄コードを検証し重複を除去する。"""

        normalized: list[str] = []

        for code in codes:
            value = code.strip()

            if not value:
                raise ValueError(
                    "銘柄コードを指定してください。"
                )

            if not value.isdigit():
                raise ValueError(
                    "銘柄コードは数字で指定してください。"
                )

            if len(value) not in {4, 5}:
                raise ValueError(
                    "銘柄コードは4桁または5桁で"
                    "指定してください。"
                )

            if value not in normalized:
                normalized.append(value)

        if not normalized:
            raise ValueError(
                "監視対象銘柄を1件以上指定してください。"
            )

        return tuple(normalized)