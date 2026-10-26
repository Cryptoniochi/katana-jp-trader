"""kabuステーション完成5分足のスレッドセーフBuffer Provider。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from threading import Lock

from app.market.models import StockPrice
from app.market.realtime_bar_aggregator import RealtimeBar


class KabuStationCompletedBarProvider:
    """WebSocket完成バーを既存RealtimeMarketMonitorへ渡す。"""

    def __init__(self) -> None:
        """空の銘柄別バッファを作成する。"""

        self._bars: dict[str, list[StockPrice]] = {}
        self._lock = Lock()

    def accept(self, bar: RealtimeBar) -> None:
        """完成RealtimeBarを既存StockPrice形式で保持する。"""

        self.accept_stock_price(
            StockPrice(
                code=bar.code,
                datetime=bar.started_at,
                open=bar.open_price,
                high=bar.high_price,
                low=bar.low_price,
                close=bar.close_price,
                volume=max(0, int(round(bar.volume))),
            )
        )

    def seed(self, prices: Iterable[StockPrice]) -> None:
        """永続化済みバーを起動時バッファへ復元する。"""

        for price in prices:
            self.accept_stock_price(price)

    def accept_stock_price(self, stock_price: StockPrice) -> None:
        """StockPriceを重複排除しながら保持する。"""

        normalized_code = stock_price.code.strip()
        if not normalized_code:
            raise ValueError("code must not be empty.")

        normalized = StockPrice(
            code=normalized_code,
            datetime=stock_price.datetime,
            open=stock_price.open,
            high=stock_price.high,
            low=stock_price.low,
            close=stock_price.close,
            volume=stock_price.volume,
        )

        with self._lock:
            code_bars = self._bars.setdefault(normalized_code, [])

            for index, existing in enumerate(code_bars):
                if existing.datetime == normalized.datetime:
                    code_bars[index] = normalized
                    break
            else:
                code_bars.append(normalized)

            code_bars.sort(key=lambda item: item.datetime)

    def __call__(
        self,
        code: str,
        target_date: date,
    ) -> list[StockPrice]:
        """指定銘柄・日付の受信済み完成バーを返す。"""

        normalized_code = code.strip()

        with self._lock:
            return [
                bar
                for bar in self._bars.get(
                    normalized_code,
                    (),
                )
                if bar.datetime.date() == target_date
            ]

    def count(
        self,
        *,
        code: str | None = None,
    ) -> int:
        """現在保持している完成バー数を返す。"""

        with self._lock:
            if code is None:
                return sum(
                    len(bars)
                    for bars in self._bars.values()
                )

            return len(
                self._bars.get(code.strip(), ())
            )
