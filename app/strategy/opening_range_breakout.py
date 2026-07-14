"""Opening Range Breakout戦略。"""

from collections import defaultdict
from datetime import date, time

from app.backtest.trade import Trade
from app.market.models import StockPrice


class OpeningRangeBreakoutStrategy:
    """寄り付き後の高値突破で買い、当日最終足で売る。"""

    def __init__(
        self,
        quantity: int = 100,
        opening_range_end: time = time(9, 15),
        commission: float = 0.0,
        slippage_rate: float = 0.0,
    ) -> None:
        """戦略条件と取引コストを設定する。"""

        if quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

        if commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if slippage_rate < 0:
            raise ValueError("スリッページ率は0以上である必要があります。")

        self.quantity = quantity
        self.opening_range_end = opening_range_end
        self.commission = commission
        self.slippage_rate = slippage_rate

    def generate_trades(
        self,
        prices: list[StockPrice],
    ) -> list[Trade]:
        """5分足からORB取引を生成する。"""

        grouped_prices: dict[
            tuple[str, date],
            list[StockPrice],
        ] = defaultdict(list)

        for price in prices:
            key = (price.code, price.datetime.date())
            grouped_prices[key].append(price)

        trades: list[Trade] = []

        for (code, _trading_date), daily_prices in grouped_prices.items():
            trade = self._generate_daily_trade(
                code=code,
                daily_prices=daily_prices,
            )

            if trade is not None:
                trades.append(trade)

        return sorted(
            trades,
            key=lambda trade: (
                trade.entry_at if trade.entry_at is not None else trade.code
            ),
        )

    def _generate_daily_trade(
        self,
        code: str,
        daily_prices: list[StockPrice],
    ) -> Trade | None:
        """1銘柄・1日分から取引を最大1件生成する。"""

        sorted_prices = sorted(
            daily_prices,
            key=lambda price: price.datetime,
        )

        opening_prices = [
            price
            for price in sorted_prices
            if price.datetime.time() <= self.opening_range_end
        ]

        breakout_candidates = [
            price
            for price in sorted_prices
            if price.datetime.time() > self.opening_range_end
        ]

        if not opening_prices or not breakout_candidates:
            return None

        opening_range_high = max(price.high for price in opening_prices)

        breakout_price = next(
            (price for price in breakout_candidates if price.high > opening_range_high),
            None,
        )

        if breakout_price is None:
            return None

        final_price = sorted_prices[-1]

        return Trade(
            code=code,
            buy_price=breakout_price.close,
            sell_price=final_price.close,
            quantity=self.quantity,
            commission=self.commission,
            slippage_rate=self.slippage_rate,
            entry_at=breakout_price.datetime,
            exit_at=final_price.datetime,
        )
