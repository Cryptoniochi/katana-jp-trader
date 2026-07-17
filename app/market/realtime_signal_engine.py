"""リアルタイム5分足を売買戦略へ適用する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.backtest.historical_models import (
    HistoricalBar,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayFrame
from app.backtest.orb_signal_strategy import (
    OrbSignalStrategy,
    OrbSignalStrategySettings,
)
from app.market.models import StockPrice
from app.market.realtime_signal_models import (
    RealtimeSignalDecision,
    RealtimeSignalProcessResult,
)
from app.trading.signal_models import TradeSignal


JST = ZoneInfo("Asia/Tokyo")


class RealtimeStrategy(Protocol):
    """リアルタイム戦略が満たすインターフェース。"""

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        """現在Frameを評価してシグナルを返す。"""

    def reset(self) -> None:
        """内部状態を初期化する。"""


StrategyFactory = Callable[[str], RealtimeStrategy]


class RealtimeSignalEngine:
    """新しい5分足だけを順番に戦略へ適用する。"""

    def __init__(
        self,
        *,
        strategy_factory: StrategyFactory | None = None,
    ) -> None:
        """銘柄別戦略生成処理を設定する。"""

        self.strategy_factory = (
            strategy_factory
            if strategy_factory is not None
            else self._default_strategy_factory
        )
        self._strategies: dict[str, RealtimeStrategy] = {}
        self._bars_by_code: dict[
            str,
            list[HistoricalBar],
        ] = defaultdict(list)
        self._last_processed_at: dict[
            str,
            datetime,
        ] = {}

    def process(
        self,
        prices: Iterable[StockPrice],
    ) -> RealtimeSignalProcessResult:
        """未処理の5分足だけを時系列順に評価する。"""

        materialized = tuple(prices)

        if not materialized:
            return RealtimeSignalProcessResult(
                decision=RealtimeSignalDecision.NO_NEW_BAR,
                input_bar_count=0,
                processed_bar_count=0,
                skipped_duplicate_count=0,
                signal_count=0,
                signals=(),
            )

        ordered = sorted(
            materialized,
            key=lambda price: (
                self._normalize_datetime(price.datetime),
                price.code,
            ),
        )
        processed_count = 0
        skipped_count = 0
        generated_signals: list[TradeSignal] = []

        for price in ordered:
            code = self._normalize_code(price.code)
            opened_at = self._normalize_datetime(
                price.datetime
            )
            last_processed = self._last_processed_at.get(code)

            if (
                last_processed is not None
                and opened_at <= last_processed
            ):
                skipped_count += 1
                continue

            bar = self._to_historical_bar(
                price,
                code=code,
                opened_at=opened_at,
            )
            visible_bars = self._bars_by_code[code]
            visible_bars.append(bar)

            strategy = self._strategies.get(code)

            if strategy is None:
                strategy = self.strategy_factory(code)
                self._strategies[code] = strategy

            frame = MarketReplayFrame(
                current_bar=bar,
                visible_bars=tuple(visible_bars),
                index=len(visible_bars) - 1,
                total_count=len(visible_bars),
            )
            signals = strategy.evaluate(frame)
            generated_signals.extend(signals)
            self._last_processed_at[code] = opened_at
            processed_count += 1

        if processed_count == 0:
            decision = RealtimeSignalDecision.NO_NEW_BAR
        elif generated_signals:
            decision = RealtimeSignalDecision.SIGNALS_GENERATED
        else:
            decision = RealtimeSignalDecision.BAR_PROCESSED

        return RealtimeSignalProcessResult(
            decision=decision,
            input_bar_count=len(materialized),
            processed_bar_count=processed_count,
            skipped_duplicate_count=skipped_count,
            signal_count=len(generated_signals),
            signals=tuple(generated_signals),
        )

    def reset(
        self,
        code: str | None = None,
    ) -> None:
        """全銘柄または指定銘柄の状態を初期化する。"""

        if code is None:
            for strategy in self._strategies.values():
                strategy.reset()

            self._strategies.clear()
            self._bars_by_code.clear()
            self._last_processed_at.clear()
            return

        normalized_code = self._normalize_code(code)
        strategy = self._strategies.pop(
            normalized_code,
            None,
        )

        if strategy is not None:
            strategy.reset()

        self._bars_by_code.pop(normalized_code, None)
        self._last_processed_at.pop(normalized_code, None)

    def last_processed_at(
        self,
        code: str,
    ) -> datetime | None:
        """指定銘柄の最終処理日時を返す。"""

        return self._last_processed_at.get(
            self._normalize_code(code)
        )

    @staticmethod
    def _default_strategy_factory(
        _code: str,
    ) -> RealtimeStrategy:
        """既定のORB戦略を作成する。"""

        return OrbSignalStrategy(
            settings=OrbSignalStrategySettings()
        )

    @staticmethod
    def _to_historical_bar(
        price: StockPrice,
        *,
        code: str,
        opened_at: datetime,
    ) -> HistoricalBar:
        """StockPriceを5分足モデルへ変換する。"""

        return HistoricalBar(
            code=code,
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=opened_at,
            open_price=float(price.open),
            high_price=float(price.high),
            low_price=float(price.low),
            close_price=float(price.close),
            volume=float(price.volume),
        )

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        """銘柄コードを検証する。"""

        normalized = code.strip()

        if not normalized.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """市場日時を日本時間へ正規化する。"""

        if value.tzinfo is None:
            return value.replace(tzinfo=JST)

        return value.astimezone(JST)
