"""イベント駆動型Opening Range Breakout戦略。"""

from dataclasses import dataclass
from datetime import date, time
from enum import StrEnum

from app.backtest.historical_models import MarketTimeframe
from app.backtest.market_replay import MarketReplayFrame
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


class OrbExitReason(StrEnum):
    """イベント駆動型ORBの決済理由。"""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    FORCE_EXIT = "force_exit"


@dataclass(frozen=True, slots=True)
class OrbSignalStrategySettings:
    """イベント駆動型ORBの戦略設定。"""

    quantity: int = 100
    opening_range_end: time = time(9, 15)
    force_exit_time: time = time(15, 30)
    stop_loss_rate: float | None = None
    take_profit_rate: float | None = None
    min_opening_range_volume: float | None = None
    min_breakout_volume: float | None = None
    breakout_volume_ratio: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_opening_range_turnover: float | None = None
    min_breakout_turnover: float | None = None

    def __post_init__(self) -> None:
        """戦略設定を検証する。"""

        if self.quantity <= 0:
            raise ValueError(
                "数量は0より大きい必要があります。"
            )

        if self.force_exit_time <= self.opening_range_end:
            raise ValueError(
                "強制決済時刻はオープニングレンジ終了後に"
                "してください。"
            )

        positive_optional = {
            "損切り率": self.stop_loss_rate,
            "利確率": self.take_profit_rate,
            "出来高倍率": self.breakout_volume_ratio,
            "最低株価": self.min_price,
            "最高株価": self.max_price,
        }

        for name, value in positive_optional.items():
            if value is not None and value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

        non_negative_optional = {
            "オープニングレンジ出来高": (
                self.min_opening_range_volume
            ),
            "ブレイク足出来高": self.min_breakout_volume,
            "オープニングレンジ売買代金": (
                self.min_opening_range_turnover
            ),
            "ブレイク足売買代金": (
                self.min_breakout_turnover
            ),
        }

        for name, value in non_negative_optional.items():
            if value is not None and value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError(
                "最低株価は最高株価以下にしてください。"
            )


@dataclass(slots=True)
class _OrbDailyState:
    """1営業日のORB内部状態。"""

    trading_date: date
    opening_high: float | None = None
    opening_volume: float = 0.0
    opening_turnover: float = 0.0
    opening_bar_count: int = 0
    entered: bool = False
    position_open: bool = False
    entry_price: float | None = None


class OrbSignalStrategy:
    """5分足を逐次評価してORBシグナルを生成する。"""

    strategy_name = "opening-range-breakout-v2"

    def __init__(
        self,
        *,
        settings: OrbSignalStrategySettings | None = None,
    ) -> None:
        """戦略設定と空の内部状態を作成する。"""

        self.settings = (
            settings
            if settings is not None
            else OrbSignalStrategySettings()
        )
        self._state: _OrbDailyState | None = None

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        """現在Frameだけを追加情報としてORBを評価する。"""

        if frame.timeframe is not MarketTimeframe.MINUTE_5:
            raise ValueError(
                "イベント駆動型ORBは5分足のみ対応しています。"
            )

        current = frame.current_bar
        current_date = current.opened_at.date()

        if (
            self._state is None
            or self._state.trading_date != current_date
        ):
            self._state = _OrbDailyState(
                trading_date=current_date
            )

        state = self._state
        current_time = current.opened_at.time()

        if current_time <= self.settings.opening_range_end:
            self._update_opening_range(frame)
            return ()

        if state.position_open:
            exit_signal = self._evaluate_exit(frame)

            if exit_signal is None:
                return ()

            state.position_open = False
            state.entry_price = None

            return (exit_signal,)

        if state.entered:
            return ()

        buy_signal = self._evaluate_entry(frame)

        if buy_signal is None:
            return ()

        state.entered = True
        state.position_open = True
        state.entry_price = current.close_price

        return (buy_signal,)

    def reset(self) -> None:
        """内部状態を初期化する。"""

        self._state = None

    def _update_opening_range(
        self,
        frame: MarketReplayFrame,
    ) -> None:
        """現在足をオープニングレンジへ加算する。"""

        assert self._state is not None

        bar = frame.current_bar
        state = self._state

        state.opening_high = (
            bar.high_price
            if state.opening_high is None
            else max(
                state.opening_high,
                bar.high_price,
            )
        )
        state.opening_volume += bar.volume
        state.opening_turnover += (
            bar.close_price * bar.volume
        )
        state.opening_bar_count += 1

    def _evaluate_entry(
        self,
        frame: MarketReplayFrame,
    ) -> TradeSignal | None:
        """ブレイク条件成立時にBUYシグナルを返す。"""

        assert self._state is not None

        bar = frame.current_bar
        state = self._state
        current_time = bar.opened_at.time()

        if current_time >= self.settings.force_exit_time:
            return None

        if (
            state.opening_high is None
            or state.opening_bar_count <= 0
        ):
            return None

        if not self._passes_opening_filters():
            return None

        if bar.high_price <= state.opening_high:
            return None

        average_opening_volume = (
            state.opening_volume
            / state.opening_bar_count
        )

        if not self._passes_breakout_filters(
            volume=bar.volume,
            close_price=bar.close_price,
            average_opening_volume=average_opening_volume,
        ):
            return None

        if not self._passes_price_filter(
            bar.close_price
        ):
            return None

        return TradeSignal(
            signal_id=self._create_signal_id(
                action=SignalAction.BUY,
                frame=frame,
            ),
            code=frame.code,
            strategy_name=self.strategy_name,
            action=SignalAction.BUY,
            generated_at=frame.replayed_at,
            signal_price=bar.close_price,
            quantity=self.settings.quantity,
            reason="opening range breakout",
            metadata={
                "opening_range_high": state.opening_high,
                "breakout_high": bar.high_price,
                "average_opening_volume": (
                    average_opening_volume
                ),
            },
        )

    def _evaluate_exit(
        self,
        frame: MarketReplayFrame,
    ) -> TradeSignal | None:
        """損切り・利確・強制決済を評価する。"""

        assert self._state is not None
        assert self._state.entry_price is not None

        bar = frame.current_bar
        entry_price = self._state.entry_price

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

        if (
            stop_price is not None
            and bar.low_price <= stop_price
        ):
            return self._create_exit_signal(
                frame=frame,
                signal_price=stop_price,
                exit_reason=OrbExitReason.STOP_LOSS,
            )

        if (
            target_price is not None
            and bar.high_price >= target_price
        ):
            return self._create_exit_signal(
                frame=frame,
                signal_price=target_price,
                exit_reason=OrbExitReason.TAKE_PROFIT,
            )

        if (
            bar.opened_at.time()
            >= self.settings.force_exit_time
        ):
            return self._create_exit_signal(
                frame=frame,
                signal_price=bar.close_price,
                exit_reason=OrbExitReason.FORCE_EXIT,
            )

        return None

    def _create_exit_signal(
        self,
        *,
        frame: MarketReplayFrame,
        signal_price: float,
        exit_reason: OrbExitReason,
    ) -> TradeSignal:
        """EXITシグナルを作成する。"""

        return TradeSignal(
            signal_id=self._create_signal_id(
                action=SignalAction.EXIT,
                frame=frame,
            ),
            code=frame.code,
            strategy_name=self.strategy_name,
            action=SignalAction.EXIT,
            generated_at=frame.replayed_at,
            signal_price=signal_price,
            quantity=self.settings.quantity,
            reason=f"orb exit: {exit_reason.value}",
            metadata={
                "exit_reason": exit_reason.value,
                "entry_price": self._state.entry_price,
            },
        )

    def _passes_opening_filters(self) -> bool:
        """オープニングレンジの流動性条件を判定する。"""

        assert self._state is not None

        if (
            self.settings.min_opening_range_volume
            is not None
            and self._state.opening_volume
            < self.settings.min_opening_range_volume
        ):
            return False

        if (
            self.settings.min_opening_range_turnover
            is not None
            and self._state.opening_turnover
            < self.settings.min_opening_range_turnover
        ):
            return False

        return True

    def _passes_breakout_filters(
        self,
        *,
        volume: float,
        close_price: float,
        average_opening_volume: float,
    ) -> bool:
        """ブレイク足の流動性条件を判定する。"""

        if (
            self.settings.min_breakout_volume is not None
            and volume < self.settings.min_breakout_volume
        ):
            return False

        if self.settings.breakout_volume_ratio is not None:
            if average_opening_volume <= 0:
                return False

            if (
                volume / average_opening_volume
                < self.settings.breakout_volume_ratio
            ):
                return False

        if (
            self.settings.min_breakout_turnover is not None
            and close_price * volume
            < self.settings.min_breakout_turnover
        ):
            return False

        return True

    def _passes_price_filter(
        self,
        price: float,
    ) -> bool:
        """エントリー価格帯を判定する。"""

        if (
            self.settings.min_price is not None
            and price < self.settings.min_price
        ):
            return False

        if (
            self.settings.max_price is not None
            and price > self.settings.max_price
        ):
            return False

        return True

    @staticmethod
    def _create_signal_id(
        *,
        action: SignalAction,
        frame: MarketReplayFrame,
    ) -> str:
        """Frameと売買指示から再現可能なIDを作成する。"""

        timestamp = frame.replayed_at.strftime(
            "%Y%m%dT%H%M%S%z"
        )

        return (
            f"orb-v2-{frame.code}-"
            f"{action.value}-{timestamp}"
        )
