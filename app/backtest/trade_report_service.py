"""約定履歴を完結トレードへ変換するサービス。"""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol

from app.backtest.trade_report_models import (
    BacktestTradeReport,
    CompletedBacktestTrade,
)
from app.trading.order_models import OrderSide
from app.trading.signal_models import TradeSignalRecord
from app.trading.trade_execution_models import (
    TradeExecutionRecord,
)


class ExecutionHistoryReader(Protocol):
    """約定履歴取得処理。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        side: OrderSide | None = None,
        order_id: str | None = None,
        signal_id: str | None = None,
    ) -> list[TradeExecutionRecord]:
        """約定履歴を新しい順に返す。"""


class SignalRecordReader(Protocol):
    """シグナル取得処理。"""

    def get(
        self,
        signal_id: str,
    ) -> TradeSignalRecord:
        """シグナルIDに一致する保存済みシグナルを返す。"""


@dataclass(slots=True)
class _OpenBuyLot:
    """未決済BUY約定の残数量。"""

    record: TradeExecutionRecord
    remaining_quantity: int


class TradeReportService:
    """BUY・SELL約定をFIFOで対応付ける。"""

    def __init__(
        self,
        *,
        execution_repository: ExecutionHistoryReader,
        signal_repository: SignalRecordReader | None = None,
    ) -> None:
        """約定Repositoryと任意のSignalRepositoryを設定する。"""

        self.execution_repository = execution_repository
        self.signal_repository = signal_repository

    def create_report(
        self,
        *,
        limit: int = 100_000,
        code: str | None = None,
    ) -> BacktestTradeReport:
        """保存済み約定から完結トレードを作成する。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        records = self.execution_repository.list_recent(
            limit=limit,
            code=code,
        )

        return self.create_report_from_records(
            tuple(records)
        )

    def create_report_from_records(
        self,
        records: tuple[TradeExecutionRecord, ...],
    ) -> BacktestTradeReport:
        """指定約定履歴から完結トレードを作成する。"""

        ordered = sorted(
            records,
            key=lambda record: (
                record.execution.executed_at,
                record.id,
                record.execution_id,
            ),
        )

        open_lots: dict[
            str,
            deque[_OpenBuyLot],
        ] = defaultdict(deque)

        trades: list[CompletedBacktestTrade] = []
        unmatched_sell_quantity = 0

        for record in ordered:
            execution = record.execution

            if execution.side is OrderSide.BUY:
                open_lots[execution.code].append(
                    _OpenBuyLot(
                        record=record,
                        remaining_quantity=execution.quantity,
                    )
                )
                continue

            remaining_sell_quantity = execution.quantity
            lots = open_lots[execution.code]

            while (
                remaining_sell_quantity > 0
                and lots
            ):
                lot = lots[0]
                matched_quantity = min(
                    remaining_sell_quantity,
                    lot.remaining_quantity,
                )

                trades.append(
                    self._create_trade(
                        buy_record=lot.record,
                        sell_record=record,
                        quantity=matched_quantity,
                        sequence=len(trades) + 1,
                    )
                )

                lot.remaining_quantity -= matched_quantity
                remaining_sell_quantity -= matched_quantity

                if lot.remaining_quantity == 0:
                    lots.popleft()

            unmatched_sell_quantity += (
                remaining_sell_quantity
            )

        unmatched_buy_quantity = sum(
            lot.remaining_quantity
            for lots in open_lots.values()
            for lot in lots
        )

        return BacktestTradeReport(
            trades=tuple(trades),
            unmatched_buy_quantity=unmatched_buy_quantity,
            unmatched_sell_quantity=unmatched_sell_quantity,
        )

    def _create_trade(
        self,
        *,
        buy_record: TradeExecutionRecord,
        sell_record: TradeExecutionRecord,
        quantity: int,
        sequence: int,
    ) -> CompletedBacktestTrade:
        """対応付けたBUY・SELLから完結トレードを作成する。"""

        buy = buy_record.execution
        sell = sell_record.execution

        buy_ratio = quantity / buy.quantity
        sell_ratio = quantity / sell.quantity

        return CompletedBacktestTrade(
            trade_id=(
                f"trade-{buy.execution_id}-"
                f"{sell.execution_id}-{sequence}"
            ),
            code=buy.code,
            quantity=quantity,
            entry_execution_id=buy.execution_id,
            exit_execution_id=sell.execution_id,
            entry_signal_id=buy.signal_id,
            exit_signal_id=sell.signal_id,
            entered_at=buy.executed_at,
            exited_at=sell.executed_at,
            entry_price=buy.execution_price,
            exit_price=sell.execution_price,
            entry_commission=(
                buy.commission * buy_ratio
            ),
            exit_commission=(
                sell.commission * sell_ratio
            ),
            entry_slippage=(
                buy.slippage * buy_ratio
            ),
            exit_slippage=(
                sell.slippage * sell_ratio
            ),
            exit_reason=self._get_exit_reason(
                sell.signal_id
            ),
        )

    def _get_exit_reason(
        self,
        signal_id: str,
    ) -> str | None:
        """決済シグナルのメタデータから理由を取得する。"""

        if self.signal_repository is None:
            return None

        signal_record = self.signal_repository.get(
            signal_id
        )
        raw_reason = signal_record.signal.metadata.get(
            "exit_reason"
        )

        if raw_reason is None:
            return None

        normalized = str(raw_reason).strip()

        return normalized or None
