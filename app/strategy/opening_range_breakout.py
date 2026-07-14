"""Opening Range Breakout戦略。"""

from collections import defaultdict
from datetime import date, datetime, time

from app.backtest.trade import ExitReason, Trade
from app.market.models import StockPrice


class OpeningRangeBreakoutStrategy:
    """寄り付き後の高値突破で買うORB戦略。"""

    def __init__(
        self,
        quantity: int = 100,
        opening_range_end: time = time(9, 15),
        stop_loss_rate: float | None = None,
        take_profit_rate: float | None = None,
        force_exit_time: time = time(15, 30),
        commission: float = 0.0,
        slippage_rate: float = 0.0,
        min_opening_range_volume: int | None = None,
        min_breakout_volume: int | None = None,
        breakout_volume_ratio: float | None = None,
    ) -> None:
        """戦略条件・取引コスト・出来高条件を設定する。"""

        if quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

        if stop_loss_rate is not None and stop_loss_rate <= 0:
            raise ValueError("損切り率は0より大きい必要があります。")

        if take_profit_rate is not None and take_profit_rate <= 0:
            raise ValueError("利確率は0より大きい必要があります。")

        if commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if slippage_rate < 0:
            raise ValueError("スリッページ率は0以上である必要があります。")

        if min_opening_range_volume is not None and min_opening_range_volume < 0:
            raise ValueError("オープニングレンジ出来高は0以上である必要があります。")

        if min_breakout_volume is not None and min_breakout_volume < 0:
            raise ValueError("ブレイク足出来高は0以上である必要があります。")

        if breakout_volume_ratio is not None and breakout_volume_ratio <= 0:
            raise ValueError("出来高倍率は0より大きい必要があります。")

        if force_exit_time <= opening_range_end:
            raise ValueError("強制決済時刻はオープニングレンジ終了後にしてください。")

        self.quantity = quantity
        self.opening_range_end = opening_range_end
        self.stop_loss_rate = stop_loss_rate
        self.take_profit_rate = take_profit_rate
        self.force_exit_time = force_exit_time
        self.commission = commission
        self.slippage_rate = slippage_rate
        self.min_opening_range_volume = min_opening_range_volume
        self.min_breakout_volume = min_breakout_volume
        self.breakout_volume_ratio = breakout_volume_ratio

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
                trade.entry_at or datetime.min,
                trade.code,
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

        if not opening_prices:
            return None

        if not self._passes_opening_volume_filter(opening_prices):
            return None

        opening_range_high = max(price.high for price in opening_prices)

        average_opening_volume = sum(price.volume for price in opening_prices) / len(
            opening_prices
        )

        breakout_index: int | None = None

        for index, price in enumerate(sorted_prices):
            is_entry_time = (
                self.opening_range_end < price.datetime.time() < self.force_exit_time
            )

            if not is_entry_time:
                continue

            if price.high <= opening_range_high:
                continue

            if not self._passes_breakout_volume_filter(
                price=price,
                average_opening_volume=average_opening_volume,
            ):
                continue

            breakout_index = index
            break

        if breakout_index is None:
            return None

        entry_bar = sorted_prices[breakout_index]
        entry_price = entry_bar.close

        exit_candidates = [
            price
            for price in sorted_prices[breakout_index + 1 :]
            if price.datetime.time() <= self.force_exit_time
        ]

        if not exit_candidates:
            return None

        sell_price, exit_bar, exit_reason = self._determine_exit(
            entry_price=entry_price,
            exit_candidates=exit_candidates,
            final_daily_price=sorted_prices[-1],
        )

        return Trade(
            code=code,
            buy_price=entry_price,
            sell_price=sell_price,
            quantity=self.quantity,
            commission=self.commission,
            slippage_rate=self.slippage_rate,
            entry_at=entry_bar.datetime,
            exit_at=exit_bar.datetime,
            exit_reason=exit_reason,
        )

    def _passes_opening_volume_filter(
        self,
        opening_prices: list[StockPrice],
    ) -> bool:
        """オープニングレンジ累計出来高の条件を判定する。"""

        if self.min_opening_range_volume is None:
            return True

        opening_volume = sum(price.volume for price in opening_prices)

        return opening_volume >= self.min_opening_range_volume

    def _passes_breakout_volume_filter(
        self,
        price: StockPrice,
        average_opening_volume: float,
    ) -> bool:
        """ブレイク足の出来高と出来高倍率を判定する。"""

        if (
            self.min_breakout_volume is not None
            and price.volume < self.min_breakout_volume
        ):
            return False

        if self.breakout_volume_ratio is None:
            return True

        if average_opening_volume <= 0:
            return False

        actual_ratio = price.volume / average_opening_volume

        return actual_ratio >= self.breakout_volume_ratio

    def _determine_exit(
        self,
        entry_price: float,
        exit_candidates: list[StockPrice],
        final_daily_price: StockPrice,
    ) -> tuple[float, StockPrice, ExitReason]:
        """損切り・利確・時間決済から決済条件を決める。"""

        stop_price = (
            entry_price * (1 - self.stop_loss_rate)
            if self.stop_loss_rate is not None
            else None
        )

        target_price = (
            entry_price * (1 + self.take_profit_rate)
            if self.take_profit_rate is not None
            else None
        )

        for price in exit_candidates:
            stop_hit = stop_price is not None and price.low <= stop_price
            target_hit = target_price is not None and price.high >= target_price

            # 5分足内の値動きの順序が分からない場合は、
            # 利益を過大評価しないよう損切りを優先する。
            if stop_hit:
                return (
                    stop_price,
                    price,
                    ExitReason.STOP_LOSS,
                )

            if target_hit:
                return (
                    target_price,
                    price,
                    ExitReason.TAKE_PROFIT,
                )

        exit_bar = exit_candidates[-1]

        if exit_bar.datetime == final_daily_price.datetime:
            exit_reason = ExitReason.END_OF_DAY
        else:
            exit_reason = ExitReason.TIME_EXIT

        return (
            exit_bar.close,
            exit_bar,
            exit_reason,
        )
