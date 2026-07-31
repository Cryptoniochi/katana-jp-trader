"""イベント駆動型Pullback Breakout戦略。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, time
from enum import StrEnum

from app.backtest.historical_models import MarketTimeframe
from app.backtest.market_replay import MarketReplayFrame
from app.backtest.orb_signal_strategy import (
    OrbSignalDiagnosticSnapshot,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


class PullbackExitReason(StrEnum):
    """Pullback Breakoutの決済理由。"""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    FORCE_EXIT = "force_exit"


class PullbackDecision(StrEnum):
    """Pullback Breakoutの判定結果。"""

    WARMUP = "warmup"
    ENTRY_TIME = "entry_time"
    UPTREND_MISSING = "uptrend_missing"
    PULLBACK_TOO_SHALLOW = "pullback_too_shallow"
    PULLBACK_TOO_DEEP = "pullback_too_deep"
    NO_REBREAKOUT = "no_rebreakout"
    VOLUME_RATIO = "volume_ratio"
    TURNOVER = "turnover"
    PRICE_RANGE = "price_range"
    BUY_SIGNAL = "buy_signal"
    POSITION_OPEN = "position_open"
    ALREADY_ENTERED = "already_entered"


@dataclass(frozen=True, slots=True)
class PullbackBreakoutSettings:
    """Pullback Breakout戦略設定。"""

    quantity: int = 100
    trend_window: int = 4
    pullback_window: int = 2
    minimum_uptrend_rate: float = 0.008
    minimum_pullback_rate: float = 0.002
    maximum_pullback_rate: float = 0.025
    breakout_volume_ratio: float | None = 1.2
    minimum_breakout_turnover: float | None = None
    minimum_price: float | None = None
    maximum_price: float | None = None
    entry_start_time: time = time(9, 30)
    entry_end_time: time = time(14, 30)
    force_exit_time: time = time(15, 20)
    stop_loss_rate: float | None = 0.01
    take_profit_rate: float | None = 0.02
    trailing_stop_rate: float | None = 0.012

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

        if self.trend_window < 2:
            raise ValueError("上昇判定期間は2本以上必要です。")

        if self.pullback_window <= 0:
            raise ValueError("押し目判定期間は1本以上必要です。")

        if self.minimum_uptrend_rate <= 0:
            raise ValueError("最低上昇率は0より大きい必要があります。")

        if self.minimum_pullback_rate < 0:
            raise ValueError("最低押し率は0以上である必要があります。")

        if self.maximum_pullback_rate <= 0:
            raise ValueError("最大押し率は0より大きい必要があります。")

        if self.minimum_pullback_rate >= self.maximum_pullback_rate:
            raise ValueError("最低押し率は最大押し率未満にしてください。")

        if not (
            self.entry_start_time
            < self.entry_end_time
            < self.force_exit_time
        ):
            raise ValueError(
                "エントリー開始・終了・強制決済時刻の順序が不正です。"
            )

        positive_optional = {
            "出来高倍率": self.breakout_volume_ratio,
            "最低株価": self.minimum_price,
            "最高株価": self.maximum_price,
            "損切り率": self.stop_loss_rate,
            "利確率": self.take_profit_rate,
            "トレーリングストップ率": self.trailing_stop_rate,
        }

        for name, value in positive_optional.items():
            if value is not None and value <= 0:
                raise ValueError(f"{name}は0より大きい必要があります。")

        if (
            self.minimum_breakout_turnover is not None
            and self.minimum_breakout_turnover < 0
        ):
            raise ValueError(
                "最低ブレイク売買代金は0以上である必要があります。"
            )

        if (
            self.minimum_price is not None
            and self.maximum_price is not None
            and self.minimum_price > self.maximum_price
        ):
            raise ValueError("最低株価は最高株価以下にしてください。")


@dataclass(slots=True)
class _PullbackDailyState:
    trading_date: date
    entered: bool = False
    position_open: bool = False
    entry_price: float | None = None
    highest_price: float | None = None


class PullbackBreakoutStrategy:
    """上昇後の押し目と再上抜けを5分足で検出する。"""

    strategy_name = "pullback-breakout-v1"

    def __init__(
        self,
        *,
        settings: PullbackBreakoutSettings | None = None,
    ) -> None:
        self.settings = (
            settings
            if settings is not None
            else PullbackBreakoutSettings()
        )
        self._state: _PullbackDailyState | None = None
        self._diagnostic_counts: Counter[str] = Counter()
        self._diagnostic_evaluation_count = 0

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        if frame.timeframe is not MarketTimeframe.MINUTE_5:
            raise ValueError(
                "Pullback Breakoutは5分足のみ対応しています。"
            )

        current = frame.current_bar
        trading_date = current.opened_at.date()

        if (
            self._state is None
            or self._state.trading_date != trading_date
        ):
            self._state = _PullbackDailyState(
                trading_date=trading_date
            )

        state = self._state

        if state.position_open:
            self._record(PullbackDecision.POSITION_OPEN)
            signal = self._evaluate_exit(frame)

            if signal is None:
                return ()

            state.position_open = False
            state.entry_price = None
            state.highest_price = None
            return (signal,)

        if state.entered:
            self._record(PullbackDecision.ALREADY_ENTERED)
            return ()

        signal = self._evaluate_entry(frame)

        if signal is None:
            return ()

        self._record(PullbackDecision.BUY_SIGNAL)
        state.entered = True
        state.position_open = True
        state.entry_price = current.close_price
        state.highest_price = current.high_price
        return (signal,)

    def reset(self) -> None:
        self._state = None
        self._diagnostic_counts.clear()
        self._diagnostic_evaluation_count = 0

    def diagnostic_snapshot(self) -> OrbSignalDiagnosticSnapshot:
        return OrbSignalDiagnosticSnapshot(
            evaluation_count=self._diagnostic_evaluation_count,
            counts=dict(self._diagnostic_counts),
        )

    def _evaluate_entry(
        self,
        frame: MarketReplayFrame,
    ) -> TradeSignal | None:
        current = frame.current_bar
        current_time = current.opened_at.time()

        if not (
            self.settings.entry_start_time
            <= current_time
            < self.settings.entry_end_time
        ):
            self._record(PullbackDecision.ENTRY_TIME)
            return None

        required = (
            self.settings.trend_window
            + self.settings.pullback_window
            + 1
        )
        bars = frame.visible_bars

        if len(bars) < required:
            self._record(PullbackDecision.WARMUP)
            return None

        trend_start = len(bars) - required
        trend_end = trend_start + self.settings.trend_window
        pullback_end = trend_end + self.settings.pullback_window

        trend_bars = bars[trend_start:trend_end]
        pullback_bars = bars[trend_end:pullback_end]

        trend_start_price = trend_bars[0].close_price
        trend_peak = max(bar.high_price for bar in trend_bars)
        uptrend_rate = (
            trend_peak / trend_start_price - 1.0
        )

        if (
            uptrend_rate
            < self.settings.minimum_uptrend_rate
            or trend_bars[-1].close_price
            <= trend_bars[0].close_price
        ):
            self._record(PullbackDecision.UPTREND_MISSING)
            return None

        pullback_low = min(
            bar.low_price
            for bar in pullback_bars
        )
        pullback_rate = (
            trend_peak - pullback_low
        ) / trend_peak

        if pullback_rate < self.settings.minimum_pullback_rate:
            self._record(
                PullbackDecision.PULLBACK_TOO_SHALLOW
            )
            return None

        if pullback_rate > self.settings.maximum_pullback_rate:
            self._record(
                PullbackDecision.PULLBACK_TOO_DEEP
            )
            return None

        pullback_high = max(
            bar.high_price
            for bar in pullback_bars
        )

        if (
            current.high_price <= pullback_high
            or current.close_price <= pullback_high
        ):
            self._record(PullbackDecision.NO_REBREAKOUT)
            return None

        average_pullback_volume = (
            sum(bar.volume for bar in pullback_bars)
            / len(pullback_bars)
        )

        if self.settings.breakout_volume_ratio is not None:
            if (
                average_pullback_volume <= 0
                or current.volume / average_pullback_volume
                < self.settings.breakout_volume_ratio
            ):
                self._record(PullbackDecision.VOLUME_RATIO)
                return None

        turnover = (
            current.close_price * current.volume
        )

        if (
            self.settings.minimum_breakout_turnover
            is not None
            and turnover
            < self.settings.minimum_breakout_turnover
        ):
            self._record(PullbackDecision.TURNOVER)
            return None

        if not self._passes_price_filter(
            current.close_price
        ):
            self._record(PullbackDecision.PRICE_RANGE)
            return None

        return TradeSignal(
            signal_id=self._signal_id(
                frame,
                SignalAction.BUY,
            ),
            code=frame.code,
            strategy_name=self.strategy_name,
            action=SignalAction.BUY,
            generated_at=frame.replayed_at,
            signal_price=current.close_price,
            quantity=self.settings.quantity,
            reason="pullback breakout",
            metadata={
                "trend_peak": trend_peak,
                "uptrend_rate": uptrend_rate,
                "pullback_low": pullback_low,
                "pullback_rate": pullback_rate,
                "pullback_high": pullback_high,
                "average_pullback_volume": (
                    average_pullback_volume
                ),
            },
        )

    def _evaluate_exit(
        self,
        frame: MarketReplayFrame,
    ) -> TradeSignal | None:
        assert self._state is not None
        assert self._state.entry_price is not None

        state = self._state
        current = frame.current_bar
        entry_price = state.entry_price
        state.highest_price = max(
            state.highest_price or current.high_price,
            current.high_price,
        )

        stop_price = (
            entry_price
            * (1.0 - self.settings.stop_loss_rate)
            if self.settings.stop_loss_rate is not None
            else None
        )
        target_price = (
            entry_price
            * (1.0 + self.settings.take_profit_rate)
            if self.settings.take_profit_rate is not None
            else None
        )
        trailing_price = (
            state.highest_price
            * (1.0 - self.settings.trailing_stop_rate)
            if self.settings.trailing_stop_rate is not None
            else None
        )

        if (
            stop_price is not None
            and current.low_price <= stop_price
        ):
            return self._exit_signal(
                frame,
                stop_price,
                PullbackExitReason.STOP_LOSS,
            )

        if (
            trailing_price is not None
            and state.highest_price > entry_price
            and current.low_price <= trailing_price
        ):
            return self._exit_signal(
                frame,
                trailing_price,
                PullbackExitReason.TRAILING_STOP,
            )

        if (
            target_price is not None
            and current.high_price >= target_price
        ):
            return self._exit_signal(
                frame,
                target_price,
                PullbackExitReason.TAKE_PROFIT,
            )

        if (
            current.opened_at.time()
            >= self.settings.force_exit_time
        ):
            return self._exit_signal(
                frame,
                current.close_price,
                PullbackExitReason.FORCE_EXIT,
            )

        return None

    def _exit_signal(
        self,
        frame: MarketReplayFrame,
        signal_price: float,
        reason: PullbackExitReason,
    ) -> TradeSignal:
        assert self._state is not None

        return TradeSignal(
            signal_id=self._signal_id(
                frame,
                SignalAction.EXIT,
            ),
            code=frame.code,
            strategy_name=self.strategy_name,
            action=SignalAction.EXIT,
            generated_at=frame.replayed_at,
            signal_price=signal_price,
            quantity=self.settings.quantity,
            reason=f"pullback exit: {reason.value}",
            metadata={
                "exit_reason": reason.value,
                "entry_price": self._state.entry_price,
                "highest_price": self._state.highest_price,
            },
        )

    def _passes_price_filter(
        self,
        price: float,
    ) -> bool:
        if (
            self.settings.minimum_price is not None
            and price < self.settings.minimum_price
        ):
            return False

        if (
            self.settings.maximum_price is not None
            and price > self.settings.maximum_price
        ):
            return False

        return True

    def _record(
        self,
        decision: PullbackDecision,
    ) -> None:
        self._diagnostic_counts[decision.value] += 1
        self._diagnostic_evaluation_count += 1

    @staticmethod
    def _signal_id(
        frame: MarketReplayFrame,
        action: SignalAction,
    ) -> str:
        timestamp = frame.replayed_at.strftime(
            "%Y%m%dT%H%M%S%z"
        )
        return (
            f"pullback-v1-{frame.code}-"
            f"{action.value}-{timestamp}"
        )
