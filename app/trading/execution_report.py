"""Execution Engineの処理結果を集計・出力する。"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.trading.execution_engine import (
    ExecutionBatchResult,
    ExecutionDecision,
    ExecutionItemResult,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
)


@dataclass(frozen=True, slots=True)
class ExecutionReportRow:
    """1件のシグナル執行結果を表す明細行。"""

    signal_id: str
    order_id: str | None
    code: str | None
    side: OrderSide | None
    decision: ExecutionDecision
    order_status: OrderStatus | None
    quantity: int | None
    filled_quantity: int
    average_fill_price: float | None
    broker_order_id: str | None
    message: str | None

    def __post_init__(self) -> None:
        """明細行の整合性を検証する。"""

        normalized_signal_id = self.signal_id.strip()

        if not normalized_signal_id:
            raise ValueError(
                "シグナルIDを指定してください。"
            )

        normalized_order_id = self._normalize_optional(
            self.order_id,
        )
        normalized_code = self._normalize_optional(
            self.code,
        )
        normalized_broker_order_id = (
            self._normalize_optional(
                self.broker_order_id,
            )
        )
        normalized_message = self._normalize_optional(
            self.message,
        )

        if (
            normalized_code is not None
            and not normalized_code.isdigit()
        ):
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if (
            normalized_code is not None
            and len(normalized_code) not in {
                4,
                5,
            }
        ):
            raise ValueError(
                "銘柄コードは4桁または5桁で"
                "指定してください。"
            )

        if (
            self.quantity is not None
            and self.quantity <= 0
        ):
            raise ValueError(
                "注文数量は0より大きい必要があります。"
            )

        if self.filled_quantity < 0:
            raise ValueError(
                "約定数量は0以上である必要があります。"
            )

        if (
            self.quantity is not None
            and self.filled_quantity > self.quantity
        ):
            raise ValueError(
                "約定数量は注文数量以下である必要があります。"
            )

        if (
            self.average_fill_price is not None
            and self.average_fill_price <= 0
        ):
            raise ValueError(
                "平均約定価格は0より大きい必要があります。"
            )

        if (
            self.filled_quantity == 0
            and self.average_fill_price is not None
        ):
            raise ValueError(
                "未約定明細には平均約定価格を"
                "設定できません。"
            )

        if (
            self.filled_quantity > 0
            and self.average_fill_price is None
        ):
            raise ValueError(
                "約定済み明細には平均約定価格が必要です。"
            )

        object.__setattr__(
            self,
            "signal_id",
            normalized_signal_id,
        )
        object.__setattr__(
            self,
            "order_id",
            normalized_order_id,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )
        object.__setattr__(
            self,
            "broker_order_id",
            normalized_broker_order_id,
        )
        object.__setattr__(
            self,
            "message",
            normalized_message,
        )

    @property
    def is_filled(self) -> bool:
        """全約定状態か返す。"""

        return self.order_status is OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """継続中注文か返す。"""

        return self.order_status in {
            OrderStatus.NEW,
            OrderStatus.QUEUED,
            OrderStatus.SENT,
            OrderStatus.PARTIALLY_FILLED,
        }

    @property
    def is_failed(self) -> bool:
        """執行または注文が失敗したか返す。"""

        return (
            self.decision is ExecutionDecision.FAILED
            or self.order_status
            in {
                OrderStatus.REJECTED,
                OrderStatus.FAILED,
            }
        )

    @staticmethod
    def _normalize_optional(
        value: str | None,
    ) -> str | None:
        """任意文字列を正規化する。"""

        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            return None

        return normalized


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Execution Engineの実行レポート。"""

    generated_at: datetime
    rows: tuple[
        ExecutionReportRow,
        ...
    ]

    def __post_init__(self) -> None:
        """生成日時を検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "レポート生成日時には"
                "タイムゾーンが必要です。"
            )

    @property
    def input_count(self) -> int:
        """処理対象件数を返す。"""

        return len(
            self.rows
        )

    @property
    def executed_count(self) -> int:
        """Broker同期まで到達した件数を返す。"""

        return sum(
            row.decision
            is not ExecutionDecision.FAILED
            for row in self.rows
        )

    @property
    def active_count(self) -> int:
        """継続中注文件数を返す。"""

        return sum(
            row.is_active
            for row in self.rows
        )

    @property
    def terminal_count(self) -> int:
        """終了状態の注文件数を返す。"""

        return sum(
            (
                row.order_status is not None
                and row.order_status.is_terminal
            )
            for row in self.rows
        )

    @property
    def filled_count(self) -> int:
        """全約定件数を返す。"""

        return sum(
            row.order_status is OrderStatus.FILLED
            for row in self.rows
        )

    @property
    def partially_filled_count(self) -> int:
        """部分約定件数を返す。"""

        return sum(
            row.order_status
            is OrderStatus.PARTIALLY_FILLED
            for row in self.rows
        )

    @property
    def cancelled_count(self) -> int:
        """取消件数を返す。"""

        return sum(
            row.order_status is OrderStatus.CANCELLED
            for row in self.rows
        )

    @property
    def rejected_count(self) -> int:
        """Broker拒否件数を返す。"""

        return sum(
            row.order_status is OrderStatus.REJECTED
            for row in self.rows
        )

    @property
    def failed_count(self) -> int:
        """執行失敗件数を返す。"""

        return sum(
            row.is_failed
            for row in self.rows
        )

    @property
    def total_order_quantity(self) -> int:
        """注文数量合計を返す。"""

        return sum(
            row.quantity or 0
            for row in self.rows
        )

    @property
    def total_filled_quantity(self) -> int:
        """約定数量合計を返す。"""

        return sum(
            row.filled_quantity
            for row in self.rows
        )

    @property
    def is_successful(self) -> bool:
        """失敗・拒否がないか返す。"""

        return self.failed_count == 0


class ExecutionReportService:
    """Execution Engineの結果をレポートへ変換する。"""

    CSV_HEADERS = (
        "signal_id",
        "order_id",
        "code",
        "side",
        "decision",
        "order_status",
        "quantity",
        "filled_quantity",
        "average_fill_price",
        "broker_order_id",
        "message",
    )

    def create(
        self,
        batch_result: ExecutionBatchResult,
        *,
        generated_at: datetime | None = None,
    ) -> ExecutionReport:
        """一括執行結果からレポートを作成する。"""

        resolved_generated_at = (
            generated_at
            if generated_at is not None
            else datetime.now(timezone.utc)
        )

        if resolved_generated_at.tzinfo is None:
            raise ValueError(
                "レポート生成日時には"
                "タイムゾーンが必要です。"
            )

        rows = tuple(
            self._create_row(
                item,
            )
            for item in batch_result.items
        )

        return ExecutionReport(
            generated_at=(
                resolved_generated_at.astimezone(
                    timezone.utc,
                )
            ),
            rows=rows,
        )

    def render_text(
        self,
        report: ExecutionReport,
    ) -> str:
        """人が確認しやすいテキストレポートを返す。"""

        lines = [
            "Execution Report",
            "================",
            (
                "Generated at     : "
                f"{report.generated_at.isoformat()}"
            ),
            (
                "Input signals    : "
                f"{report.input_count}"
            ),
            (
                "Executed         : "
                f"{report.executed_count}"
            ),
            (
                "Active orders    : "
                f"{report.active_count}"
            ),
            (
                "Terminal orders  : "
                f"{report.terminal_count}"
            ),
            (
                "Filled           : "
                f"{report.filled_count}"
            ),
            (
                "Partially filled : "
                f"{report.partially_filled_count}"
            ),
            (
                "Cancelled        : "
                f"{report.cancelled_count}"
            ),
            (
                "Rejected         : "
                f"{report.rejected_count}"
            ),
            (
                "Failed           : "
                f"{report.failed_count}"
            ),
            (
                "Order quantity   : "
                f"{report.total_order_quantity}"
            ),
            (
                "Filled quantity  : "
                f"{report.total_filled_quantity}"
            ),
            "",
            "Details",
            "-------",
        ]

        if not report.rows:
            lines.append(
                "No execution results."
            )

            return "\n".join(
                lines
            )

        for row in report.rows:
            lines.append(
                self._render_row(
                    row,
                )
            )

        return "\n".join(
            lines
        )

    def write_csv(
        self,
        report: ExecutionReport,
        output_path: Path,
    ) -> Path:
        """レポート明細をUTF-8のCSVへ保存する。"""

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with output_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=self.CSV_HEADERS,
            )

            writer.writeheader()

            for row in report.rows:
                writer.writerow(
                    self._row_to_csv_dict(
                        row,
                    )
                )

        return output_path

    @staticmethod
    def _create_row(
        item: ExecutionItemResult,
    ) -> ExecutionReportRow:
        """Execution明細をレポート行へ変換する。"""

        order_record = item.order_record

        if order_record is not None:
            return ExecutionReportRow(
                signal_id=item.signal_id,
                order_id=order_record.order_id,
                code=order_record.code,
                side=order_record.order.side,
                decision=item.decision,
                order_status=order_record.status,
                quantity=order_record.order.quantity,
                filled_quantity=(
                    order_record.filled_quantity
                ),
                average_fill_price=(
                    order_record.average_fill_price
                ),
                broker_order_id=(
                    order_record.broker_order_id
                ),
                message=item.message,
            )

        signal_record = item.signal_record

        return ExecutionReportRow(
            signal_id=item.signal_id,
            order_id=item.order_id,
            code=(
                signal_record.code
                if signal_record is not None
                else None
            ),
            side=None,
            decision=item.decision,
            order_status=None,
            quantity=(
                signal_record.signal.quantity
                if signal_record is not None
                else None
            ),
            filled_quantity=0,
            average_fill_price=None,
            broker_order_id=None,
            message=item.message,
        )

    @staticmethod
    def _render_row(
        row: ExecutionReportRow,
    ) -> str:
        """1件の明細を1行のテキストへ変換する。"""

        code = (
            row.code
            if row.code is not None
            else "-"
        )
        side = (
            row.side.value.upper()
            if row.side is not None
            else "-"
        )
        status = (
            row.order_status.value.upper()
            if row.order_status is not None
            else "-"
        )
        order_id = (
            row.order_id
            if row.order_id is not None
            else "-"
        )

        line = (
            f"{code} "
            f"{side} "
            f"{status} "
            f"signal={row.signal_id} "
            f"order={order_id} "
            f"filled={row.filled_quantity}"
        )

        if row.message is not None:
            line += (
                f" message={row.message}"
            )

        return line

    @staticmethod
    def _row_to_csv_dict(
        row: ExecutionReportRow,
    ) -> dict[str, object]:
        """明細行をCSV出力用辞書へ変換する。"""

        return {
            "signal_id": row.signal_id,
            "order_id": row.order_id or "",
            "code": row.code or "",
            "side": (
                row.side.value
                if row.side is not None
                else ""
            ),
            "decision": row.decision.value,
            "order_status": (
                row.order_status.value
                if row.order_status is not None
                else ""
            ),
            "quantity": (
                row.quantity
                if row.quantity is not None
                else ""
            ),
            "filled_quantity": (
                row.filled_quantity
            ),
            "average_fill_price": (
                row.average_fill_price
                if row.average_fill_price is not None
                else ""
            ),
            "broker_order_id": (
                row.broker_order_id or ""
            ),
            "message": row.message or "",
        }