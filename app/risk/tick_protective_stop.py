"""最新ティックでPaper保有を保護する独立ストップ。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Callable, Protocol

from app.market.market_data_provider import MarketDataTick
from app.trading.broker_adapter import (
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.signal_models import SignalAction, TradeSignal


class ProtectiveStopBroker(Protocol):
    """保護ストップが参照するBroker契約。"""

    def list_positions(self) -> list[BrokerPosition]:
        """現在保有を返す。"""


class ExternalSignalExecutor(Protocol):
    """既存Paper経路で外部生成Signalを執行する契約。"""

    def execute_external_signal(
        self,
        signal: TradeSignal,
        *,
        current_price: float,
        continue_on_error: bool = False,
    ) -> bool:
        """約定保存まで成功した場合にTrueを返す。"""


@dataclass(frozen=True, slots=True)
class TickProtectiveStopSettings:
    """ティック保護ストップ設定。"""

    stop_loss_rate: float = 0.01

    def __post_init__(self) -> None:
        if not 0 < self.stop_loss_rate < 1:
            raise ValueError(
                "保護ストップ率は0より大きく1未満で指定してください。"
            )


@dataclass(frozen=True, slots=True)
class TickProtectiveStopResult:
    """1サイクルの保護ストップ処理結果。"""

    consumed_tick_count: int
    evaluated_position_count: int
    triggered_count: int
    executed_count: int


class LatestMarketTickBuffer:
    """WebSocketスレッドから最新ティックだけを安全に受け渡す。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._latest_by_code: dict[str, MarketDataTick] = {}

    def accept(self, tick: MarketDataTick) -> None:
        """銘柄ごとの最新ティックを保存する。"""

        with self._lock:
            previous = self._latest_by_code.get(tick.code)
            if previous is None or tick.observed_at >= previous.observed_at:
                self._latest_by_code[tick.code] = tick

    def drain(self) -> tuple[MarketDataTick, ...]:
        """蓄積中の最新ティックを時系列順で取り出す。"""

        with self._lock:
            ticks = tuple(self._latest_by_code.values())
            self._latest_by_code.clear()

        return tuple(
            sorted(ticks, key=lambda item: (item.observed_at, item.code))
        )


class TickProtectiveStopService:
    """最新ティックを評価し、既存Paper経路へ保護EXITを流す。"""

    strategy_name = "tick-protective-stop-v1"

    def __init__(
        self,
        *,
        tick_buffer: LatestMarketTickBuffer,
        broker: ProtectiveStopBroker,
        signal_executor: ExternalSignalExecutor,
        market_price_updater: Callable[[str, float], object],
        position_closed_notifier: Callable[[str], object],
        settings: TickProtectiveStopSettings | None = None,
    ) -> None:
        self.tick_buffer = tick_buffer
        self.broker = broker
        self.signal_executor = signal_executor
        self.market_price_updater = market_price_updater
        self.position_closed_notifier = position_closed_notifier
        self.settings = settings or TickProtectiveStopSettings()

    def process_pending(self) -> TickProtectiveStopResult:
        """最新ティックを価格反映し、閾値到達保有を決済する。"""

        ticks = self.tick_buffer.drain()
        if not ticks:
            return TickProtectiveStopResult(0, 0, 0, 0)

        latest = {tick.code: tick for tick in ticks}
        for tick in latest.values():
            self.market_price_updater(tick.code, tick.price)

        positions = tuple(self.broker.list_positions())
        triggered_count = 0
        executed_count = 0

        for position in positions:
            tick = latest.get(position.code)
            if tick is None or not self._is_triggered(position, tick.price):
                continue

            triggered_count += 1
            stop_price = self._stop_price(position)
            signal = TradeSignal(
                signal_id=self._signal_id(position.code, tick),
                code=position.code,
                strategy_name=self.strategy_name,
                action=SignalAction.EXIT,
                generated_at=tick.observed_at,
                signal_price=tick.price,
                quantity=position.quantity,
                reason="tick protective stop loss",
                metadata={
                    "exit_reason": "tick_protective_stop",
                    "entry_price": position.average_price,
                    "trigger_price": tick.price,
                    "stop_price": stop_price,
                    "stop_loss_rate": self.settings.stop_loss_rate,
                    "position_side": position.side.value,
                    "source": "kabu_station_tick",
                },
            )
            executed = self.signal_executor.execute_external_signal(
                signal,
                current_price=tick.price,
                continue_on_error=True,
            )
            if not executed:
                continue

            executed_count += 1
            self.position_closed_notifier(position.code)

        return TickProtectiveStopResult(
            consumed_tick_count=len(ticks),
            evaluated_position_count=len(positions),
            triggered_count=triggered_count,
            executed_count=executed_count,
        )

    def _is_triggered(
        self,
        position: BrokerPosition,
        price: float,
    ) -> bool:
        stop_price = self._stop_price(position)
        if position.side is BrokerPositionSide.LONG:
            return price <= stop_price
        return price >= stop_price

    def _stop_price(self, position: BrokerPosition) -> float:
        direction = (
            1 - self.settings.stop_loss_rate
            if position.side is BrokerPositionSide.LONG
            else 1 + self.settings.stop_loss_rate
        )
        return position.average_price * direction

    @staticmethod
    def _signal_id(code: str, tick: MarketDataTick) -> str:
        stamp = tick.observed_at.strftime("%Y%m%dT%H%M%S%f%z")
        return f"tick-protective-stop-{code}-exit-{stamp}"
