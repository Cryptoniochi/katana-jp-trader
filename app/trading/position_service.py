"""約定履歴を現在ポジションへ反映する。"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.trading.broker_adapter import BrokerPositionSide
from app.trading.order_models import OrderSide
from app.trading.position_models import (
    TradingPosition,
    TradingPositionRecord,
)
from app.trading.position_repository import PositionRepository
from app.trading.trade_execution_models import TradeExecutionRecord


class PositionServiceError(RuntimeError):
    """ポジション反映処理の基底例外。"""


class InsufficientPositionError(PositionServiceError):
    """売却数量が保有数量を超えたことを表す。"""


@dataclass(frozen=True, slots=True)
class PositionApplicationResult:
    """1件の約定をポジションへ反映した結果。"""

    execution_id: str
    applied: bool
    position_record: TradingPositionRecord | None
    realized_profit_loss: float

    @property
    def position_closed(self) -> bool:
        """全売却によりポジションが解消されたか返す。"""

        return self.applied and self.position_record is None


class PositionService:
    """約定履歴から現在ポジションを更新する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        position_repository: PositionRepository,
    ) -> None:
        """DBパスとPositionRepositoryを設定する。"""

        self.database_path = database_path
        self.position_repository = position_repository

    def apply_execution(
        self,
        execution_record: TradeExecutionRecord,
    ) -> PositionApplicationResult:
        """未反映の約定を現在ポジションへ1度だけ反映する。"""

        execution = execution_record.execution

        if self._was_applied(execution.execution_id):
            current = self.position_repository.get_by_identity(
                code=execution.code,
                side=BrokerPositionSide.LONG,
            )
            return PositionApplicationResult(
                execution_id=execution.execution_id,
                applied=False,
                position_record=current,
                realized_profit_loss=0.0,
            )

        try:
            if execution.side is OrderSide.BUY:
                result = self._apply_buy(execution_record)
            else:
                result = self._apply_sell(execution_record)

            self._mark_applied(
                execution_id=execution.execution_id,
                applied_at=execution.executed_at,
            )
            return result

        except Exception:
            raise

    def _apply_buy(
        self,
        execution_record: TradeExecutionRecord,
    ) -> PositionApplicationResult:
        """買い約定で新規作成または買い増しする。"""

        execution = execution_record.execution
        current = self.position_repository.get_by_identity(
            code=execution.code,
            side=BrokerPositionSide.LONG,
        )

        if current is None:
            position = TradingPosition(
                position_id=(
                    f"position-{execution.code}-long"
                ),
                code=execution.code,
                side=BrokerPositionSide.LONG,
                quantity=execution.quantity,
                average_cost=execution.execution_price,
                realized_profit_loss=0.0,
                opened_at=execution.executed_at,
            )
            saved = self.position_repository.create(position)
        else:
            total_quantity = (
                current.quantity + execution.quantity
            )
            weighted_average = (
                current.position.average_cost
                * current.quantity
                + execution.execution_price
                * execution.quantity
            ) / total_quantity

            position = TradingPosition(
                position_id=current.position_id,
                code=current.code,
                side=current.side,
                quantity=total_quantity,
                average_cost=weighted_average,
                realized_profit_loss=(
                    current.position.realized_profit_loss
                ),
                opened_at=current.position.opened_at,
            )
            saved = self.position_repository.update(position)

        return PositionApplicationResult(
            execution_id=execution.execution_id,
            applied=True,
            position_record=saved,
            realized_profit_loss=0.0,
        )

    def _apply_sell(
        self,
        execution_record: TradeExecutionRecord,
    ) -> PositionApplicationResult:
        """売り約定で数量を減らし実現損益を加算する。"""

        execution = execution_record.execution
        current = self.position_repository.get_by_identity(
            code=execution.code,
            side=BrokerPositionSide.LONG,
        )

        if current is None:
            raise InsufficientPositionError(
                "売却対象ポジションが存在しません。 "
                f"code={execution.code}"
            )

        if execution.quantity > current.quantity:
            raise InsufficientPositionError(
                "売却数量が保有数量を超えています。 "
                f"code={execution.code} "
                f"required={execution.quantity} "
                f"available={current.quantity}"
            )

        realized = (
            execution.execution_price
            - current.position.average_cost
        ) * execution.quantity

        accumulated_realized = (
            current.position.realized_profit_loss
            + realized
        )
        remaining_quantity = (
            current.quantity - execution.quantity
        )

        if remaining_quantity == 0:
            self.position_repository.delete(
                current.position_id
            )
            saved = None
        else:
            position = TradingPosition(
                position_id=current.position_id,
                code=current.code,
                side=current.side,
                quantity=remaining_quantity,
                average_cost=current.position.average_cost,
                realized_profit_loss=accumulated_realized,
                opened_at=current.position.opened_at,
            )
            saved = self.position_repository.update(position)

        return PositionApplicationResult(
            execution_id=execution.execution_id,
            applied=True,
            position_record=saved,
            realized_profit_loss=realized,
        )

    def _was_applied(self, execution_id: str) -> bool:
        """約定が既にポジションへ反映済みか返す。"""

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM position_applied_executions
                    WHERE execution_id = ?
                    LIMIT 1
                    """,
                    (execution_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise PositionServiceError(
                "約定反映状態を確認できませんでした。 "
                f"execution_id={execution_id}"
            ) from error

        return row is not None

    def _mark_applied(
        self,
        *,
        execution_id: str,
        applied_at: datetime,
    ) -> None:
        """約定をポジション反映済みとして保存する。"""

        normalized_applied_at = applied_at.astimezone(
            timezone.utc
        )

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                connection.execute(
                    """
                    INSERT INTO position_applied_executions (
                        execution_id,
                        applied_at
                    )
                    VALUES (?, ?)
                    """,
                    (
                        execution_id,
                        normalized_applied_at.isoformat(),
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError:
            return
        except sqlite3.Error as error:
            raise PositionServiceError(
                "約定反映状態を保存できませんでした。 "
                f"execution_id={execution_id}"
            ) from error
