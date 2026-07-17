"""バックテスト完結トレードと集計結果のモデル。"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class CompletedBacktestTrade:
    """BUY約定とSELL約定を対応付けた完結トレード。"""

    trade_id: str
    code: str
    quantity: int
    entry_execution_id: str
    exit_execution_id: str
    entry_signal_id: str
    exit_signal_id: str
    entered_at: datetime
    exited_at: datetime
    entry_price: float
    exit_price: float
    entry_commission: float
    exit_commission: float
    entry_slippage: float
    exit_slippage: float
    exit_reason: str | None = None

    def __post_init__(self) -> None:
        """完結トレードの内容を検証して正規化する。"""

        normalized_trade_id = self.trade_id.strip()
        normalized_code = self.code.strip()
        normalized_entry_execution_id = (
            self.entry_execution_id.strip()
        )
        normalized_exit_execution_id = (
            self.exit_execution_id.strip()
        )
        normalized_entry_signal_id = (
            self.entry_signal_id.strip()
        )
        normalized_exit_signal_id = (
            self.exit_signal_id.strip()
        )
        normalized_exit_reason = (
            self.exit_reason.strip()
            if self.exit_reason is not None
            else None
        )

        required = {
            "トレードID": normalized_trade_id,
            "銘柄コード": normalized_code,
            "エントリー約定ID": normalized_entry_execution_id,
            "決済約定ID": normalized_exit_execution_id,
            "エントリーシグナルID": normalized_entry_signal_id,
            "決済シグナルID": normalized_exit_signal_id,
        }

        for name, value in required.items():
            if not value:
                raise ValueError(
                    f"{name}を指定してください。"
                )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if self.quantity <= 0:
            raise ValueError(
                "数量は0より大きい必要があります。"
            )

        if self.entered_at.tzinfo is None:
            raise ValueError(
                "エントリー日時にはタイムゾーンが必要です。"
            )

        if self.exited_at.tzinfo is None:
            raise ValueError(
                "決済日時にはタイムゾーンが必要です。"
            )

        if self.exited_at < self.entered_at:
            raise ValueError(
                "決済日時はエントリー日時以後である必要があります。"
            )

        if self.entry_price <= 0:
            raise ValueError(
                "エントリー価格は0より大きい必要があります。"
            )

        if self.exit_price <= 0:
            raise ValueError(
                "決済価格は0より大きい必要があります。"
            )

        for name, value in {
            "エントリー手数料": self.entry_commission,
            "決済手数料": self.exit_commission,
            "エントリースリッページ": self.entry_slippage,
            "決済スリッページ": self.exit_slippage,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if normalized_exit_reason == "":
            normalized_exit_reason = None

        object.__setattr__(
            self,
            "trade_id",
            normalized_trade_id,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )
        object.__setattr__(
            self,
            "entry_execution_id",
            normalized_entry_execution_id,
        )
        object.__setattr__(
            self,
            "exit_execution_id",
            normalized_exit_execution_id,
        )
        object.__setattr__(
            self,
            "entry_signal_id",
            normalized_entry_signal_id,
        )
        object.__setattr__(
            self,
            "exit_signal_id",
            normalized_exit_signal_id,
        )
        object.__setattr__(
            self,
            "exit_reason",
            normalized_exit_reason,
        )

    @property
    def gross_profit_loss(self) -> float:
        """売買価格差による損益を返す。"""

        return (
            self.exit_price - self.entry_price
        ) * self.quantity

    @property
    def total_cost(self) -> float:
        """手数料とスリッページの合計を返す。"""

        return (
            self.entry_commission
            + self.exit_commission
            + self.entry_slippage
            + self.exit_slippage
        )

    @property
    def net_profit_loss(self) -> float:
        """コスト控除後損益を返す。"""

        return self.gross_profit_loss - self.total_cost

    @property
    def return_rate(self) -> float:
        """取得金額に対するコスト控除後収益率を返す。"""

        acquisition_value = (
            self.entry_price * self.quantity
        )

        return self.net_profit_loss / acquisition_value

    @property
    def holding_period(self) -> timedelta:
        """保有期間を返す。"""

        return self.exited_at - self.entered_at

    @property
    def holding_seconds(self) -> float:
        """保有秒数を返す。"""

        return self.holding_period.total_seconds()

    @property
    def is_winner(self) -> bool:
        """利益トレードか返す。"""

        return self.net_profit_loss > 0

    @property
    def is_loser(self) -> bool:
        """損失トレードか返す。"""

        return self.net_profit_loss < 0

    @property
    def is_flat(self) -> bool:
        """損益ゼロか返す。"""

        return self.net_profit_loss == 0


@dataclass(frozen=True, slots=True)
class BacktestTradeReport:
    """約定履歴から作成した完結トレード一覧。"""

    trades: tuple[CompletedBacktestTrade, ...]
    unmatched_buy_quantity: int
    unmatched_sell_quantity: int

    def __post_init__(self) -> None:
        """集計結果を検証する。"""

        if self.unmatched_buy_quantity < 0:
            raise ValueError(
                "未決済買い数量は0以上である必要があります。"
            )

        if self.unmatched_sell_quantity < 0:
            raise ValueError(
                "未対応売り数量は0以上である必要があります。"
            )

    @property
    def trade_count(self) -> int:
        """完結トレード件数を返す。"""

        return len(self.trades)

    @property
    def total_net_profit_loss(self) -> float:
        """完結トレードの純損益合計を返す。"""

        return sum(
            trade.net_profit_loss
            for trade in self.trades
        )

    @property
    def winning_trade_count(self) -> int:
        """利益トレード件数を返す。"""

        return sum(
            trade.is_winner
            for trade in self.trades
        )

    @property
    def losing_trade_count(self) -> int:
        """損失トレード件数を返す。"""

        return sum(
            trade.is_loser
            for trade in self.trades
        )

    @property
    def flat_trade_count(self) -> int:
        """損益ゼロのトレード件数を返す。"""

        return sum(
            trade.is_flat
            for trade in self.trades
        )
