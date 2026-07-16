"""Execution Reportの集計・テキスト・CSV出力テスト。"""

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.trading.execution_engine import (
    ExecutionBatchResult,
    ExecutionDecision,
    ExecutionItemResult,
)
from app.trading.execution_report import (
    ExecutionReportRow,
    ExecutionReportService,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
    TradeOrderRecord,
)


GENERATED_AT = datetime(
    2026,
    7,
    16,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_order_record(
    *,
    order_id: str = "order-001",
    signal_id: str = "signal-001",
    code: str = "7203",
    status: OrderStatus = OrderStatus.FILLED,
    quantity: int = 100,
    filled_quantity: int = 100,
    average_fill_price: float | None = 2500.0,
) -> TradeOrderRecord:
    """レポート用の注文レコードを作成する。"""

    terminal = status.is_terminal

    return TradeOrderRecord(
        id=1,
        order=TradeOrder(
            order_id=order_id,
            signal_id=signal_id,
            code=code,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity,
        ),
        status=status,
        filled_quantity=filled_quantity,
        average_fill_price=average_fill_price,
        broker_order_id="paper-order-00000001",
        status_reason="paper order filled",
        error_message=None,
        created_at=GENERATED_AT,
        updated_at=GENERATED_AT,
        submitted_at=GENERATED_AT,
        completed_at=(
            GENERATED_AT
            if terminal
            else None
        ),
    )


def create_item(
    *,
    signal_id: str = "signal-001",
    decision: ExecutionDecision = (
        ExecutionDecision.TERMINAL
    ),
    order_record: TradeOrderRecord | None = None,
    message: str | None = None,
) -> ExecutionItemResult:
    """レポート用Execution明細を作成する。"""

    resolved_order_record = (
        order_record
        if order_record is not None
        else create_order_record(
            signal_id=signal_id,
        )
    )

    return ExecutionItemResult(
        decision=decision,
        signal_id=signal_id,
        order_id=(
            resolved_order_record.order_id
            if resolved_order_record is not None
            else None
        ),
        signal_record=None,
        order_record=resolved_order_record,
        order_creation_result=None,
        broker_sync_result=None,
        message=message,
    )


def test_service_creates_filled_report() -> None:
    """全約定結果をレポートへ変換する。"""

    service = ExecutionReportService()

    report = service.create(
        ExecutionBatchResult(
            items=(
                create_item(),
            )
        ),
        generated_at=GENERATED_AT,
    )

    assert report.generated_at == GENERATED_AT
    assert report.input_count == 1
    assert report.executed_count == 1
    assert report.active_count == 0
    assert report.terminal_count == 1
    assert report.filled_count == 1
    assert report.partially_filled_count == 0
    assert report.cancelled_count == 0
    assert report.rejected_count == 0
    assert report.failed_count == 0
    assert report.total_order_quantity == 100
    assert report.total_filled_quantity == 100
    assert report.is_successful is True

    row = report.rows[0]

    assert row.signal_id == "signal-001"
    assert row.order_id == "order-001"
    assert row.code == "7203"
    assert row.side is OrderSide.BUY
    assert row.order_status is OrderStatus.FILLED
    assert row.quantity == 100
    assert row.filled_quantity == 100
    assert row.average_fill_price == pytest.approx(
        2500.0
    )
    assert row.is_filled is True


def test_service_counts_active_order() -> None:
    """SENT注文を継続中として集計する。"""

    order_record = create_order_record(
        status=OrderStatus.SENT,
        filled_quantity=0,
        average_fill_price=None,
    )

    report = ExecutionReportService().create(
        ExecutionBatchResult(
            items=(
                create_item(
                    decision=ExecutionDecision.ACTIVE,
                    order_record=order_record,
                ),
            )
        ),
        generated_at=GENERATED_AT,
    )

    assert report.active_count == 1
    assert report.terminal_count == 0
    assert report.filled_count == 0
    assert report.failed_count == 0
    assert report.rows[0].is_active is True


def test_service_counts_partially_filled_order() -> None:
    """部分約定注文を集計する。"""

    order_record = create_order_record(
        status=OrderStatus.PARTIALLY_FILLED,
        filled_quantity=40,
        average_fill_price=2501.0,
    )

    report = ExecutionReportService().create(
        ExecutionBatchResult(
            items=(
                create_item(
                    decision=ExecutionDecision.ACTIVE,
                    order_record=order_record,
                ),
            )
        ),
        generated_at=GENERATED_AT,
    )

    assert report.active_count == 1
    assert report.partially_filled_count == 1
    assert report.total_filled_quantity == 40


def test_service_counts_rejected_order_as_failure() -> None:
    """Broker拒否注文を失敗として集計する。"""

    order_record = create_order_record(
        status=OrderStatus.REJECTED,
        filled_quantity=0,
        average_fill_price=None,
    )

    report = ExecutionReportService().create(
        ExecutionBatchResult(
            items=(
                create_item(
                    decision=ExecutionDecision.TERMINAL,
                    order_record=order_record,
                ),
            )
        ),
        generated_at=GENERATED_AT,
    )

    assert report.rejected_count == 1
    assert report.failed_count == 1
    assert report.is_successful is False
    assert report.rows[0].is_failed is True


def test_service_handles_failed_item_without_order() -> None:
    """注文作成前の失敗を明細へ残す。"""

    failed_item = ExecutionItemResult(
        decision=ExecutionDecision.FAILED,
        signal_id="signal-failed",
        order_id=None,
        signal_record=None,
        order_record=None,
        order_creation_result=None,
        broker_sync_result=None,
        message="buying power unavailable",
    )

    report = ExecutionReportService().create(
        ExecutionBatchResult(
            items=(
                failed_item,
            )
        ),
        generated_at=GENERATED_AT,
    )

    assert report.input_count == 1
    assert report.executed_count == 0
    assert report.failed_count == 1
    assert report.total_order_quantity == 0
    assert report.total_filled_quantity == 0

    row = report.rows[0]

    assert row.signal_id == "signal-failed"
    assert row.order_id is None
    assert row.code is None
    assert row.order_status is None
    assert row.message == (
        "buying power unavailable"
    )


def test_service_aggregates_multiple_results() -> None:
    """複数の状態をまとめて集計する。"""

    filled = create_item(
        signal_id="signal-filled",
        order_record=create_order_record(
            order_id="order-filled",
            signal_id="signal-filled",
            code="7203",
            status=OrderStatus.FILLED,
            quantity=100,
            filled_quantity=100,
            average_fill_price=2500.0,
        ),
    )

    active = create_item(
        signal_id="signal-active",
        decision=ExecutionDecision.ACTIVE,
        order_record=create_order_record(
            order_id="order-active",
            signal_id="signal-active",
            code="8306",
            status=OrderStatus.SENT,
            quantity=200,
            filled_quantity=0,
            average_fill_price=None,
        ),
    )

    failed = ExecutionItemResult(
        decision=ExecutionDecision.FAILED,
        signal_id="signal-failed",
        order_id=None,
        signal_record=None,
        order_record=None,
        order_creation_result=None,
        broker_sync_result=None,
        message="risk rejected",
    )

    report = ExecutionReportService().create(
        ExecutionBatchResult(
            items=(
                filled,
                active,
                failed,
            )
        ),
        generated_at=GENERATED_AT,
    )

    assert report.input_count == 3
    assert report.executed_count == 2
    assert report.active_count == 1
    assert report.terminal_count == 1
    assert report.filled_count == 1
    assert report.failed_count == 1
    assert report.total_order_quantity == 300
    assert report.total_filled_quantity == 100


def test_render_text_contains_summary_and_details() -> None:
    """テキストに集計と銘柄別明細を含める。"""

    service = ExecutionReportService()

    report = service.create(
        ExecutionBatchResult(
            items=(
                create_item(),
            )
        ),
        generated_at=GENERATED_AT,
    )

    text = service.render_text(
        report
    )

    assert "Execution Report" in text
    assert "Input signals    : 1" in text
    assert "Filled           : 1" in text
    assert "7203 BUY FILLED" in text
    assert "signal=signal-001" in text
    assert "order=order-001" in text


def test_render_text_handles_empty_report() -> None:
    """空結果を明示する。"""

    service = ExecutionReportService()

    report = service.create(
        ExecutionBatchResult(
            items=(),
        ),
        generated_at=GENERATED_AT,
    )

    text = service.render_text(
        report
    )

    assert report.input_count == 0
    assert report.is_successful is True
    assert "No execution results." in text


def test_write_csv_saves_execution_rows(
    tmp_path: Path,
) -> None:
    """Execution明細をCSVへ保存する。"""

    service = ExecutionReportService()

    report = service.create(
        ExecutionBatchResult(
            items=(
                create_item(),
            )
        ),
        generated_at=GENERATED_AT,
    )

    output_path = (
        tmp_path
        / "reports"
        / "execution.csv"
    )

    returned_path = service.write_csv(
        report,
        output_path,
    )

    assert returned_path == output_path
    assert output_path.exists()

    with output_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as input_file:
        rows = list(
            csv.DictReader(
                input_file
            )
        )

    assert len(rows) == 1

    row = rows[0]

    assert row["signal_id"] == "signal-001"
    assert row["order_id"] == "order-001"
    assert row["code"] == "7203"
    assert row["side"] == "buy"
    assert row["decision"] == "terminal"
    assert row["order_status"] == "filled"
    assert row["quantity"] == "100"
    assert row["filled_quantity"] == "100"
    assert row["average_fill_price"] == "2500.0"


def test_service_rejects_naive_generated_time() -> None:
    """タイムゾーンなしレポート生成日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        ExecutionReportService().create(
            ExecutionBatchResult(
                items=(),
            ),
            generated_at=datetime(
                2026,
                7,
                16,
                9,
                30,
            ),
        )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "signal_id": " ",
            },
            "シグナルID",
        ),
        (
            {
                "code": "ABC",
            },
            "数字",
        ),
        (
            {
                "quantity": 0,
            },
            "注文数量",
        ),
        (
            {
                "filled_quantity": -1,
            },
            "約定数量",
        ),
        (
            {
                "filled_quantity": 101,
            },
            "注文数量以下",
        ),
        (
            {
                "average_fill_price": -1.0,
            },
            "平均約定価格",
        ),
    ],
)
def test_report_row_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なレポート明細を拒否する。"""

    base_arguments: dict[str, object] = {
        "signal_id": "signal-001",
        "order_id": "order-001",
        "code": "7203",
        "side": OrderSide.BUY,
        "decision": ExecutionDecision.ACTIVE,
        "order_status": OrderStatus.SENT,
        "quantity": 100,
        "filled_quantity": 0,
        "average_fill_price": None,
        "broker_order_id": "paper-order-00000001",
        "message": None,
    }

    base_arguments.update(
        arguments
    )

    with pytest.raises(
        (
            TypeError,
            ValueError,
        ),
        match=message,
    ):
        ExecutionReportRow(
            **base_arguments
        )


def test_report_row_requires_price_when_filled() -> None:
    """約定数量がある明細には平均価格を要求する。"""

    with pytest.raises(
        ValueError,
        match="平均約定価格",
    ):
        ExecutionReportRow(
            signal_id="signal-001",
            order_id="order-001",
            code="7203",
            side=OrderSide.BUY,
            decision=ExecutionDecision.ACTIVE,
            order_status=(
                OrderStatus.PARTIALLY_FILLED
            ),
            quantity=100,
            filled_quantity=40,
            average_fill_price=None,
            broker_order_id=(
                "paper-order-00000001"
            ),
            message=None,
        )