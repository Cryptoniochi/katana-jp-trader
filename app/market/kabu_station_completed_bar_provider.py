"""kabuステーション完成5分足のスレッドセーフBuffer Provider。"""

from __future__ import annotations

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

        stock_price = StockPrice(
            code=bar.code,
            datetime=bar.started_at,
            open=bar.open_price,
            high=bar.high_price,
            low=bar.low_price,
            close=bar.close_price,
            volume=max(0, int(round(bar.volume))),
        )

        with self._lock:
            code_bars = self._bars.setdefault(
                stock_price.code,
                [],
            )

            for index, existing in enumerate(code_bars):
                if existing.datetime == stock_price.datetime:
                    code_bars[index] = stock_price
                    break
            else:
                code_bars.append(stock_price)

            code_bars.sort(
                key=lambda item: item.datetime
            )

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
