"""Risk Gate通過後のPaper注文をShadow台帳へ安全に複製する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
    BacktestQueueExecutionItemResult,
)
from app.live.shadow_broker import (
    ShadowOrderRecordResult,
)
from app.trading.order_models import TradeOrder


class ShadowOrderRecorder(Protocol):
    """Shadow注文計画を冪等に記録する処理。"""

    def record_order(
        self,
        order: TradeOrder,
    ) -> ShadowOrderRecordResult:
        """注文計画を記録する。"""


class PaperShadowReplicationDecision(StrEnum):
    """Paper注文1件のShadow複製結果。"""

    RECORDED = "recorded"
    EXISTING = "existing"
    SKIPPED = "skipped"
    FAILED = "failed"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class PaperShadowReplicationItemResult:
    """Paper注文1件とShadow注文計画の照合結果。"""

    decision: PaperShadowReplicationDecision
    paper_order: TradeOrder
    shadow_result: ShadowOrderRecordResult | None
    message: str | None = None

    def __post_init__(self) -> None:
        normalized_message = (
            self.message.strip()
            if self.message is not None
            else None
        )

        if normalized_message == "":
            normalized_message = None

        if (
            self.decision
            in {
                PaperShadowReplicationDecision.RECORDED,
                PaperShadowReplicationDecision.EXISTING,
            }
            and self.shadow_result is None
        ):
            raise ValueError(
                "記録結果にはShadow注文結果が必要です。"
            )

        if (
            self.decision
            in {
                PaperShadowReplicationDecision.SKIPPED,
                PaperShadowReplicationDecision.FAILED,
                PaperShadowReplicationDecision.MISMATCH,
            }
            and normalized_message is None
        ):
            raise ValueError(
                "未記録結果には理由が必要です。"
            )

        object.__setattr__(
            self,
            "message",
            normalized_message,
        )

    @property
    def is_successful(self) -> bool:
        """Shadow記録と照合が成功したか返す。"""

        return self.decision in {
            PaperShadowReplicationDecision.RECORDED,
            PaperShadowReplicationDecision.EXISTING,
        }

    @property
    def is_failed(self) -> bool:
        """Shadow処理自体が失敗したか返す。"""

        return (
            self.decision
            is PaperShadowReplicationDecision.FAILED
        )

    @property
    def is_mismatch(self) -> bool:
        """PaperとShadowの注文内容が不一致か返す。"""

        return (
            self.decision
            is PaperShadowReplicationDecision.MISMATCH
        )


@dataclass(frozen=True, slots=True)
class PaperShadowReplicationBatchResult:
    """1回のPaper注文バッチに対するShadow複製結果。"""

    items: tuple[PaperShadowReplicationItemResult, ...]

    @property
    def input_count(self) -> int:
        """確認したPaper注文件数を返す。"""

        return len(self.items)

    @property
    def recorded_count(self) -> int:
        """新規記録した件数を返す。"""

        return sum(
            item.decision
            is PaperShadowReplicationDecision.RECORDED
            for item in self.items
        )

    @property
    def existing_count(self) -> int:
        """既存記録を再利用した件数を返す。"""

        return sum(
            item.decision
            is PaperShadowReplicationDecision.EXISTING
            for item in self.items
        )

    @property
    def skipped_count(self) -> int:
        """Paper失敗等で複製対象外になった件数を返す。"""

        return sum(
            item.decision
            is PaperShadowReplicationDecision.SKIPPED
            for item in self.items
        )

    @property
    def failed_count(self) -> int:
        """Shadow記録に失敗した件数を返す。"""

        return sum(
            item.is_failed
            for item in self.items
        )

    @property
    def mismatch_count(self) -> int:
        """注文内容が一致しなかった件数を返す。"""

        return sum(
            item.is_mismatch
            for item in self.items
        )

    @property
    def replicated_count(self) -> int:
        """正常にShadowへ存在する件数を返す。"""

        return self.recorded_count + self.existing_count

    @property
    def is_consistent(self) -> bool:
        """失敗・不一致がないか返す。"""

        return (
            self.failed_count == 0
            and self.mismatch_count == 0
        )


class PaperShadowReplicationService:
    """Paper Broker処理後の注文だけをShadow台帳へ複製する。"""

    def __init__(
        self,
        *,
        shadow_recorder: ShadowOrderRecorder,
    ) -> None:
        self.shadow_recorder = shadow_recorder

    def replicate(
        self,
        execution_result: BacktestQueueExecutionBatchResult,
        *,
        continue_on_error: bool = True,
    ) -> PaperShadowReplicationBatchResult:
        """Paper実行結果を複製し、Shadow障害をPaperから分離する。"""

        items = tuple(
            self._replicate_item(
                item,
                continue_on_error=continue_on_error,
            )
            for item in execution_result.items
        )

        return PaperShadowReplicationBatchResult(
            items=items
        )

    def _replicate_item(
        self,
        item: BacktestQueueExecutionItemResult,
        *,
        continue_on_error: bool,
    ) -> PaperShadowReplicationItemResult:
        order = item.queued_order.order_record.order

        if item.is_failed:
            return PaperShadowReplicationItemResult(
                decision=(
                    PaperShadowReplicationDecision.SKIPPED
                ),
                paper_order=order,
                shadow_result=None,
                message=(
                    item.message
                    or "Paper注文が失敗したため複製しません。"
                ),
            )

        if item.broker_sync_result is None:
            return PaperShadowReplicationItemResult(
                decision=(
                    PaperShadowReplicationDecision.SKIPPED
                ),
                paper_order=order,
                shadow_result=None,
                message=(
                    "Paper Broker同期結果がないため"
                    "複製しません。"
                ),
            )

        try:
            shadow_result = (
                self.shadow_recorder.record_order(order)
            )

            if not self._orders_match(
                paper_order=order,
                shadow_result=shadow_result,
            ):
                return PaperShadowReplicationItemResult(
                    decision=(
                        PaperShadowReplicationDecision.MISMATCH
                    ),
                    paper_order=order,
                    shadow_result=shadow_result,
                    message=(
                        "Paper注文とShadow注文計画が"
                        "一致しません。"
                    ),
                )

            decision = (
                PaperShadowReplicationDecision.RECORDED
                if shadow_result.was_recorded
                else PaperShadowReplicationDecision.EXISTING
            )

            return PaperShadowReplicationItemResult(
                decision=decision,
                paper_order=order,
                shadow_result=shadow_result,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return PaperShadowReplicationItemResult(
                decision=(
                    PaperShadowReplicationDecision.FAILED
                ),
                paper_order=order,
                shadow_result=None,
                message=str(error),
            )

    @staticmethod
    def _orders_match(
        *,
        paper_order: TradeOrder,
        shadow_result: ShadowOrderRecordResult,
    ) -> bool:
        """注文全項目とBroker共通Snapshotの一致を確認する。"""

        snapshot = shadow_result.snapshot

        return (
            shadow_result.order == paper_order
            and snapshot.client_order_id
            == paper_order.order_id
            and snapshot.code == paper_order.code
            and snapshot.side is paper_order.side
            and snapshot.quantity == paper_order.quantity
            and snapshot.filled_quantity == 0
            and snapshot.average_fill_price is None
        )
