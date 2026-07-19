"""東京市場の状態に応じてApplication起動を制御する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from time import sleep
from typing import Protocol

from app.market.market_clock import (
    TokyoMarketClock,
    TokyoMarketClockSnapshot,
)
from app.market.market_session import (
    TokyoMarketSession,
)


NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]
ApplicationRunner = Callable[[], int]
StatusObserver = Callable[
    [str, TokyoMarketClockSnapshot],
    None,
]


class MarketSessionRunDecision(StrEnum):
    """市場状態に基づく運用ランナーの最終判断。"""

    EXECUTED = "executed"
    SKIPPED_NON_BUSINESS_DAY = (
        "skipped_non_business_day"
    )
    SKIPPED_AFTER_CLOSE = "skipped_after_close"
    STOP_REQUESTED = "stop_requested"


@dataclass(frozen=True, slots=True)
class MarketSessionRunResult:
    """市場セッション運用ランナーの結果。"""

    decision: MarketSessionRunDecision
    snapshot: TokyoMarketClockSnapshot
    application_exit_code: int | None = None
    waited_seconds: float = 0.0

    def __post_init__(self) -> None:
        """結果の整合性を検証する。"""

        if self.waited_seconds < 0:
            raise ValueError(
                "待機秒数は0以上である必要があります。"
            )

        if (
            self.decision
            is MarketSessionRunDecision.EXECUTED
            and self.application_exit_code is None
        ):
            raise ValueError(
                "実行結果にはApplication終了コードが必要です。"
            )

        if (
            self.decision
            is not MarketSessionRunDecision.EXECUTED
            and self.application_exit_code is not None
        ):
            raise ValueError(
                "未実行結果にはApplication終了コードを"
                "設定できません。"
            )


class MarketClock(Protocol):
    """運用ランナーが利用するMarket Clock。"""

    def snapshot(
        self,
        observed_at: datetime,
    ) -> TokyoMarketClockSnapshot:
        """現在の市場状態を返す。"""


class MarketSessionRunner:
    """東京市場の状態を確認してApplicationを起動する。"""

    def __init__(
        self,
        *,
        market_clock: MarketClock | None = None,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
        stop_requested: StopPredicate | None = None,
        maximum_sleep_seconds: float = 30.0,
        wait_for_open: bool = True,
        status_observer: StatusObserver | None = None,
    ) -> None:
        """時計・待機・停止処理を設定する。"""

        if maximum_sleep_seconds <= 0:
            raise ValueError(
                "最大待機単位は0より大きい必要があります。"
            )

        self.market_clock = (
            market_clock
            if market_clock is not None
            else TokyoMarketClock()
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
        self.maximum_sleep_seconds = (
            maximum_sleep_seconds
        )
        self.wait_for_open = wait_for_open
        self.status_observer = status_observer

    def run(
        self,
        application_runner: ApplicationRunner,
    ) -> MarketSessionRunResult:
        """市場状態に応じて待機・スキップ・実行する。"""

        waited_seconds = 0.0

        while True:
            snapshot = self.market_clock.snapshot(
                self._current_time()
            )

            if self.stop_requested():
                self._observe(
                    "stop_requested",
                    snapshot,
                )
                return MarketSessionRunResult(
                    decision=(
                        MarketSessionRunDecision
                        .STOP_REQUESTED
                    ),
                    snapshot=snapshot,
                    waited_seconds=waited_seconds,
                )

            if not snapshot.business_day:
                self._observe(
                    "non_business_day",
                    snapshot,
                )
                return MarketSessionRunResult(
                    decision=(
                        MarketSessionRunDecision
                        .SKIPPED_NON_BUSINESS_DAY
                    ),
                    snapshot=snapshot,
                    waited_seconds=waited_seconds,
                )

            if (
                snapshot.session
                is TokyoMarketSession.AFTER_CLOSE
            ):
                self._observe(
                    "after_close",
                    snapshot,
                )
                return MarketSessionRunResult(
                    decision=(
                        MarketSessionRunDecision
                        .SKIPPED_AFTER_CLOSE
                    ),
                    snapshot=snapshot,
                    waited_seconds=waited_seconds,
                )

            if snapshot.is_open:
                self._observe(
                    "market_open",
                    snapshot,
                )
                exit_code = int(
                    application_runner()
                )
                return MarketSessionRunResult(
                    decision=(
                        MarketSessionRunDecision.EXECUTED
                    ),
                    snapshot=snapshot,
                    application_exit_code=exit_code,
                    waited_seconds=waited_seconds,
                )

            if not self.wait_for_open:
                self._observe(
                    "waiting_disabled",
                    snapshot,
                )
                return MarketSessionRunResult(
                    decision=(
                        MarketSessionRunDecision
                        .STOP_REQUESTED
                    ),
                    snapshot=snapshot,
                    waited_seconds=waited_seconds,
                )

            self._observe(
                "waiting_for_open",
                snapshot,
            )
            sleep_seconds = min(
                self.maximum_sleep_seconds,
                max(
                    0.1,
                    snapshot.wait_seconds,
                ),
            )
            self.sleeper(sleep_seconds)
            waited_seconds += sleep_seconds

    def _current_time(self) -> datetime:
        """タイムゾーン付き現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current

    def _observe(
        self,
        status: str,
        snapshot: TokyoMarketClockSnapshot,
    ) -> None:
        """状態Observerを安全に呼び出す。"""

        if self.status_observer is None:
            return

        self.status_observer(
            status,
            snapshot,
        )
