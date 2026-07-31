"""保存済み日足候補を5分足で執行するHigh Breakout戦略。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, time
from enum import StrEnum
from typing import Protocol

from app.backtest.historical_models import MarketTimeframe
from app.backtest.market_replay import MarketReplayFrame
from app.backtest.orb_signal_strategy import OrbSignalDiagnosticSnapshot
from app.strategy.high_breakout_models import HighBreakoutCandidate
from app.trading.signal_models import SignalAction, TradeSignal


class HighBreakoutCandidateProvider(Protocol):
    def __call__(
        self,
        code: str,
        trading_date: date,
    ) -> HighBreakoutCandidate | None:
        ...


class HighBreakoutExitReason(StrEnum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    FORCE_EXIT = "force_exit"


@dataclass(frozen=True, slots=True)
class HighBreakoutStrategySettings:
    quantity: int = 100
    intraday_lookback_bars: int = 4
    breakout_volume_ratio: float | None = 1.2
    entry_start_time: time = time(9, 30)
    entry_end_time: time = time(14, 30)
    force_exit_time: time = time(15, 20)
    stop_loss_rate: float | None = 0.012
    take_profit_rate: float | None = 0.025
    trailing_stop_rate: float | None = 0.015

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")
        if self.intraday_lookback_bars < 2:
            raise ValueError("日中判定期間は2本以上必要です。")
        if not (
            self.entry_start_time
            < self.entry_end_time
            < self.force_exit_time
        ):
            raise ValueError("売買時刻設定の順序が不正です。")
        for name, value in {
            "出来高倍率": self.breakout_volume_ratio,
            "損切り率": self.stop_loss_rate,
            "利確率": self.take_profit_rate,
            "トレーリング率": self.trailing_stop_rate,
        }.items():
            if value is not None and value <= 0:
                raise ValueError(f"{name}は0より大きい必要があります。")


@dataclass(slots=True)
class _State:
    trading_date: date
    candidate: HighBreakoutCandidate | None
    entered: bool = False
    position_open: bool = False
    entry_price: float | None = None
    highest_price: float | None = None


class HighBreakoutStrategy:
    strategy_name = "high-breakout-v1"

    def __init__(
        self,
        *,
        candidate_provider: HighBreakoutCandidateProvider,
        settings: HighBreakoutStrategySettings | None = None,
    ) -> None:
        self.candidate_provider = candidate_provider
        self.settings = settings or HighBreakoutStrategySettings()
        self._state: _State | None = None
        self._counts: Counter[str] = Counter()
        self._evaluations = 0

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        if frame.timeframe is not MarketTimeframe.MINUTE_5:
            raise ValueError("High Breakoutは5分足のみ対応しています。")

        trading_date = frame.current_bar.opened_at.date()
        if self._state is None or self._state.trading_date != trading_date:
            self._state = _State(
                trading_date=trading_date,
                candidate=self.candidate_provider(
                    frame.code,
                    trading_date,
                ),
            )

        state = self._state
        if state.candidate is None:
            self._record("no_candidate")
            return ()

        if state.position_open:
            self._record("position_open")
            exit_signal = self._exit(frame)
            if exit_signal is None:
                return ()
            state.position_open = False
            state.entry_price = None
            state.highest_price = None
            return (exit_signal,)

        if state.entered:
            self._record("already_entered")
            return ()

        current = frame.current_bar
        if not (
            self.settings.entry_start_time
            <= current.opened_at.time()
            < self.settings.entry_end_time
        ):
            self._record("entry_time")
            return ()

        required = self.settings.intraday_lookback_bars + 1
        if len(frame.visible_bars) < required:
            self._record("warmup")
            return ()

        previous = frame.visible_bars[-required:-1]
        previous_high = max(bar.high_price for bar in previous)

        if (
            current.high_price <= previous_high
            or current.close_price <= previous_high
        ):
            self._record("no_intraday_breakout")
            return ()

        average_volume = sum(bar.volume for bar in previous) / len(previous)
        if (
            self.settings.breakout_volume_ratio is not None
            and (
                average_volume <= 0
                or current.volume / average_volume
                < self.settings.breakout_volume_ratio
            )
        ):
            self._record("volume_ratio")
            return ()

        state.entered = True
        state.position_open = True
        state.entry_price = current.close_price
        state.highest_price = current.high_price
        self._record("buy_signal")

        return (
            TradeSignal(
                signal_id=self._signal_id(frame, SignalAction.BUY),
                code=frame.code,
                strategy_name=self.strategy_name,
                action=SignalAction.BUY,
                generated_at=frame.replayed_at,
                signal_price=current.close_price,
                quantity=self.settings.quantity,
                reason="high breakout intraday confirmation",
                metadata={
                    "candidate_score": state.candidate.score,
                    "candidate_date": state.candidate.trading_date.isoformat(),
                    "breakout_types": tuple(
                        value.value
                        for value in state.candidate.breakout_types
                    ),
                    "intraday_high": previous_high,
                },
            ),
        )

    def _exit(
        self,
        frame: MarketReplayFrame,
    ) -> TradeSignal | None:
        assert self._state is not None
        assert self._state.entry_price is not None

        current = frame.current_bar
        entry = self._state.entry_price
        self._state.highest_price = max(
            self._state.highest_price or current.high_price,
            current.high_price,
        )
        highest = self._state.highest_price

        checks = (
            (
                self.settings.stop_loss_rate is not None
                and current.low_price
                <= entry * (1 - self.settings.stop_loss_rate),
                entry * (1 - (self.settings.stop_loss_rate or 0)),
                HighBreakoutExitReason.STOP_LOSS,
            ),
            (
                self.settings.trailing_stop_rate is not None
                and highest > entry
                and current.low_price
                <= highest * (1 - self.settings.trailing_stop_rate),
                highest * (1 - (self.settings.trailing_stop_rate or 0)),
                HighBreakoutExitReason.TRAILING_STOP,
            ),
            (
                self.settings.take_profit_rate is not None
                and current.high_price
                >= entry * (1 + self.settings.take_profit_rate),
                entry * (1 + (self.settings.take_profit_rate or 0)),
                HighBreakoutExitReason.TAKE_PROFIT,
            ),
            (
                current.opened_at.time()
                >= self.settings.force_exit_time,
                current.close_price,
                HighBreakoutExitReason.FORCE_EXIT,
            ),
        )

        for matched, price, reason in checks:
            if matched:
                return TradeSignal(
                    signal_id=self._signal_id(
                        frame,
                        SignalAction.EXIT,
                    ),
                    code=frame.code,
                    strategy_name=self.strategy_name,
                    action=SignalAction.EXIT,
                    generated_at=frame.replayed_at,
                    signal_price=price,
                    quantity=self.settings.quantity,
                    reason=f"high breakout exit: {reason.value}",
                    metadata={
                        "exit_reason": reason.value,
                        "entry_price": entry,
                        "highest_price": highest,
                    },
                )

        return None

    def reset(self) -> None:
        self._state = None
        self._counts.clear()
        self._evaluations = 0

    def diagnostic_snapshot(self) -> OrbSignalDiagnosticSnapshot:
        return OrbSignalDiagnosticSnapshot(
            evaluation_count=self._evaluations,
            counts=dict(self._counts),
        )

    def _record(self, name: str) -> None:
        self._counts[name] += 1
        self._evaluations += 1

    @staticmethod
    def _signal_id(
        frame: MarketReplayFrame,
        action: SignalAction,
    ) -> str:
        stamp = frame.replayed_at.strftime("%Y%m%dT%H%M%S%z")
        return (
            f"high-breakout-v1-{frame.code}-"
            f"{action.value}-{stamp}"
        )
