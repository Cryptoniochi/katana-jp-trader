"""市場終了時にPaper Brokerの全ポジションを決済する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.trading.broker_adapter import BrokerPosition
from app.trading.order_models import OrderType
from app.trading.signal_models import SignalAction, TradeSignal


class EndOfDayBroker(Protocol):
    """強制決済対象のBroker。"""

    def list_positions(self) -> list[BrokerPosition]:
        """現在の保有ポジションを返す。"""


class EndOfDayOrderQueueService(Protocol):
    """強制決済シグナルを注文キューへ登録する。"""

    def enqueue_signal(
        self,
        signal: TradeSignal,
        *,
        order_type: OrderType,
        continue_on_error: bool,
    ):
        """シグナルを注文へ変換してキューへ登録する。"""


class EndOfDayExecutionService(Protocol):
    """キュー先頭の注文を約定・保存する。"""

    def execute_next(self):
        """次の注文を執行する。"""


class EndOfDayPortfolioUpdateService(Protocol):
    """保存済み約定をポジションと資産へ反映する。"""

    def apply_execution(
        self,
        execution_record,
        *,
        equity_curve_limit: int = 10_000,
    ):
        """1件の約定をPortfolioへ反映する。"""


@dataclass(frozen=True, slots=True)
class EndOfDayLiquidationResult:
    """市場終了時の全決済結果。"""

    requested_count: int
    executed_count: int
    remaining_position_count: int
    execution_records: tuple[object, ...]

    @property
    def completed(self) -> bool:
        """全ポジションが決済されたか返す。"""

        return self.remaining_position_count == 0


class EndOfDayLiquidationService:
    """既存の注文・約定・Portfolio更新経路で全決済する。"""

    def __init__(
        self,
        *,
        broker: EndOfDayBroker,
        order_queue_service: EndOfDayOrderQueueService,
        execution_service: EndOfDayExecutionService,
        portfolio_update_service: EndOfDayPortfolioUpdateService,
        now_provider=None,
    ) -> None:
        self.broker = broker
        self.order_queue_service = order_queue_service
        self.execution_service = execution_service
        self.portfolio_update_service = portfolio_update_service
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def close_all_positions(self) -> EndOfDayLiquidationResult:
        """現在の全ポジションを成行EXITで決済する。"""

        execution_records: list[object] = []
        generated_at = self._current_time()
        requested_count = 0
        attempt = 0

        while True:
            positions = tuple(self.broker.list_positions())
            if not positions:
                break
            if attempt >= 10_000:
                raise RuntimeError(
                    "市場終了時の決済が上限回数を超えました。"
                )

            position = positions[0]
            attempt += 1
            signal = TradeSignal(
                signal_id=(
                    "end-of-day-"
                    f"{generated_at.date().isoformat()}-"
                    f"{position.code}-{position.side.value}-"
                    f"{attempt}"
                ),
                code=position.code,
                strategy_name="end-of-day-liquidation",
                action=SignalAction.EXIT,
                generated_at=generated_at,
                signal_price=float(position.market_price),
                quantity=int(position.quantity),
                reason="Market close forced liquidation",
            )

            queued = self.order_queue_service.enqueue_signal(
                signal,
                order_type=OrderType.MARKET,
                continue_on_error=False,
            )

            if bool(getattr(queued, "is_failed", False)):
                raise RuntimeError(
                    getattr(queued, "message", None)
                    or (
                        "市場終了時の決済注文登録に失敗しました。 "
                        f"code={position.code}"
                    )
                )

            requested_count += 1
            target_order_id = self._order_id(queued)
            target_executed = False

            while not target_executed:
                executed = self.execution_service.execute_next()

                if executed is None:
                    raise RuntimeError(
                        "市場終了時の決済注文が執行されませんでした。 "
                        f"code={position.code}"
                    )

                if bool(getattr(executed, "is_failed", False)):
                    raise RuntimeError(
                        getattr(executed, "message", None)
                        or (
                            "市場終了時の決済注文に失敗しました。 "
                            f"code={position.code}"
                        )
                    )

                execution_record = getattr(
                    executed,
                    "execution_record",
                    None,
                )

                if execution_record is not None:
                    self.portfolio_update_service.apply_execution(
                        execution_record
                    )
                    execution_records.append(execution_record)

                executed_order_id = self._order_id(executed)
                target_executed = (
                    target_order_id is None
                    or executed_order_id == target_order_id
                )

                if target_executed and execution_record is None:
                    raise RuntimeError(
                        "市場終了時の決済約定が保存されませんでした。 "
                        f"code={position.code}"
                    )

        remaining = tuple(self.broker.list_positions())

        if remaining:
            remaining_codes = ",".join(
                position.code
                for position in remaining
            )
            raise RuntimeError(
                "市場終了後も未決済ポジションが残っています。 "
                f"count={len(remaining)} "
                f"codes={remaining_codes}"
            )

        return EndOfDayLiquidationResult(
            requested_count=requested_count,
            executed_count=len(execution_records),
            remaining_position_count=0,
            execution_records=tuple(execution_records),
        )

    @staticmethod
    def _order_id(value: object) -> str | None:
        direct = getattr(value, "order_id", None)
        if direct:
            return str(direct)
        for attribute in ("order_record", "queued_order"):
            nested = getattr(value, attribute, None)
            nested_id = getattr(nested, "order_id", None)
            if nested_id:
                return str(nested_id)
        return None

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)
