"""Execution Engineの結果を約定台帳へ保存する。"""

from dataclasses import dataclass
from typing import Protocol

from app.trading.execution_engine import (
    ExecutionBatchResult,
    ExecutionEngine,
    ExecutionItemResult,
)
from app.trading.order_models import OrderType
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)
from app.trading.trade_execution_repository import (
    DuplicateTradeExecutionError,
    TradeExecutionRepository,
)


class ExecutionBatchRunner(Protocol):
    """Execution Engineの一括実行インターフェース。"""

    def run_pending(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = True,
    ) -> ExecutionBatchResult:
        """未処理シグナルを実行する。"""


@dataclass(frozen=True, slots=True)
class TradeExecutionServiceResult:
    """Execution実行と約定保存の結果。"""

    batch_result: ExecutionBatchResult
    execution_records: tuple[
        TradeExecutionRecord,
        ...
    ]

    @property
    def saved_execution_count(self) -> int:
        """保存した約定履歴件数を返す。"""

        return len(self.execution_records)

    @property
    def is_successful(self) -> bool:
        """Execution失敗がないか返す。"""

        return self.batch_result.is_successful


class TradeExecutionService:
    """Execution Engineと約定台帳を接続する。"""

    def __init__(
        self,
        *,
        execution_engine: ExecutionBatchRunner,
        execution_repository: TradeExecutionRepository,
        broker_name: str,
        commission_per_execution: float = 0.0,
        slippage_per_execution: float = 0.0,
    ) -> None:
        """必要な依存関係と約定コストを設定する。"""

        normalized_broker_name = broker_name.strip()

        if not normalized_broker_name:
            raise ValueError(
                "Broker名を指定してください。"
            )

        if commission_per_execution < 0:
            raise ValueError(
                "約定手数料は0以上である必要があります。"
            )

        if slippage_per_execution < 0:
            raise ValueError(
                "約定スリッページは0以上である必要があります。"
            )

        self.execution_engine = execution_engine
        self.execution_repository = execution_repository
        self.broker_name = normalized_broker_name
        self.commission_per_execution = commission_per_execution
        self.slippage_per_execution = slippage_per_execution

    def run_pending(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = True,
    ) -> TradeExecutionServiceResult:
        """未処理シグナルを実行し、新規約定分を保存する。"""

        batch_result = self.execution_engine.run_pending(
            limit=limit,
            code=code,
            strategy_name=strategy_name,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            continue_on_error=continue_on_error,
        )

        records: list[TradeExecutionRecord] = []

        for item in batch_result.items:
            record = self._save_new_fill(item)

            if record is not None:
                records.append(record)

        return TradeExecutionServiceResult(
            batch_result=batch_result,
            execution_records=tuple(records),
        )

    def _save_new_fill(
        self,
        item: ExecutionItemResult,
    ) -> TradeExecutionRecord | None:
        """1件のExecution結果から未保存約定分を保存する。"""

        order_record = item.order_record
        sync_result = item.broker_sync_result

        if (
            order_record is None
            or sync_result is None
            or sync_result.broker_snapshot is None
        ):
            return None

        snapshot = sync_result.broker_snapshot

        if (
            snapshot.filled_quantity <= 0
            or snapshot.average_fill_price is None
        ):
            return None

        existing_records = (
            self.execution_repository.find_by_order(
                order_record.order_id
            )
        )

        recorded_quantity = sum(
            record.execution.quantity
            for record in existing_records
        )

        new_quantity = (
            snapshot.filled_quantity
            - recorded_quantity
        )

        if new_quantity <= 0:
            return None

        execution_id = (
            f"{snapshot.broker_order_id}:"
            f"{snapshot.filled_quantity}"
        )

        execution = TradeExecution(
            execution_id=execution_id,
            signal_id=order_record.signal_id,
            order_id=order_record.order_id,
            broker_order_id=snapshot.broker_order_id,
            code=order_record.code,
            side=order_record.order.side,
            quantity=new_quantity,
            execution_price=snapshot.average_fill_price,
            executed_at=snapshot.updated_at,
            broker_name=self.broker_name,
            commission=self.commission_per_execution,
            slippage=self.slippage_per_execution,
            metadata={
                "cumulative_filled_quantity": (
                    snapshot.filled_quantity
                ),
                "order_status": snapshot.status.value,
            },
        )

        try:
            return self.execution_repository.save(
                execution
            )
        except DuplicateTradeExecutionError:
            return self.execution_repository.get(
                execution_id
            )


def ensure_execution_engine(
    engine: ExecutionEngine,
) -> ExecutionEngine:
    """型検査用途としてExecutionEngineをそのまま返す。"""

    return engine
