"""始値で買い、終値で売る単純な戦略。"""

from collections import defaultdict
from datetime import date

from app.backtest.trade import Trade
from app.market.models import StockPrice


class BuyOpenSellCloseStrategy:
    """最初の足の始値で買い、最後の足の終値で売る。"""

    def __init__(
        self,
        quantity: int = 100,
        commission: float = 0.0,
        slippage_rate: float = 0.0,
    ) -> None:
        """数量・手数料・スリッページ率を設定する。"""

        if quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

        if commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if slippage_rate < 0:
            raise ValueError("スリッページ率は0以上である必要があります。")

        self.quantity = quantity
        self.commission = commission
        self.slippage_rate = slippage_rate

    def generate_trades(
        self,
        prices: list[StockPrice],
    ) -> list[Trade]:
        """株価を銘柄・日付ごとにまとめ、取引を生成する。"""

        grouped_prices: dict[
            tuple[str, date],
            list[StockPrice],
        ] = defaultdict(list)

        for price in prices:
            key = (
                price.code,
                price.datetime.date(),
            )
            grouped_prices[key].append(price)

        trades: list[Trade] = []

        for (code, _trading_date), group in grouped_prices.items():
            sorted_prices = sorted(
                group,
                key=lambda price: price.datetime,
            )

            first_price = sorted_prices[0]
            last_price = sorted_prices[-1]

            trades.append(
                Trade(
                    code=code,
                    buy_price=first_price.open,
                    sell_price=last_price.close,
                    quantity=self.quantity,
                    commission=self.commission,
                    slippage_rate=self.slippage_rate,
                )
            )

        return sorted(
            trades,
            key=lambda trade: trade.code,
        )
