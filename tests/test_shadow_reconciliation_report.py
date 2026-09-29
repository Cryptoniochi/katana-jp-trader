"""Shadow日次照合レポートのテスト。"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.live.paper_shadow_replication import (
    PaperShadowReplicationService,
)
from app.live.shadow_broker import (
    ShadowBroker,
    ShadowBrokerSettings,
)
from app.live.shadow_reconciliation_report import (
    ShadowReconciliationReportWriter,
)
from app.trading.order_models import (
    OrderSide,
    OrderType,
    TradeOrder,
)


NOW = datetime(2026, 9, 30, 0, 30, tzinfo=timezone.utc)


def create_order() -> TradeOrder:
    return TradeOrder(
        order_id="paper-order-001",
        signal_id="signal-001",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
    )


def execution_batch():
    order = create_order()
    return SimpleNamespace(
        items=(
            SimpleNamespace(
                queued_order=SimpleNamespace(
                    order_record=SimpleNamespace(
                        order=order
                    )
                ),
                is_failed=False,
                broker_sync_result=object(),
                message=None,
            ),
        )
    )


def test_initial_report_is_waiting_and_enabled(tmp_path) -> None:
    report_path = tmp_path / "reconciliation.json"
    writer = ShadowReconciliationReportWriter(
        report_path=report_path,
        now_provider=lambda: NOW,
    )

    payload = writer.initialize()

    assert payload["trading_date"] == "2026-09-30"
    assert payload["state"] == "waiting"
    assert payload["enabled"] is True
    assert payload["input_count"] == 0


def test_initialization_error_is_reported_as_attention(
    tmp_path,
) -> None:
    report_path = tmp_path / "reconciliation.json"
    writer = ShadowReconciliationReportWriter(
        report_path=report_path,
        now_provider=lambda: NOW,
    )

    payload = writer.record_initialization_error(
        OSError("shadow ledger unavailable")
    )

    assert payload["state"] == "attention"
    assert payload["consistent"] is False
    assert payload["issue_count"] == 1
    assert payload["initialization_error"] == (
        "shadow ledger unavailable"
    )


def test_report_accumulates_idempotent_shadow_result(tmp_path) -> None:
    report_path = tmp_path / "reconciliation.json"
    writer = ShadowReconciliationReportWriter(
        report_path=report_path,
        now_provider=lambda: NOW,
    )
    service = PaperShadowReplicationService(
        shadow_recorder=ShadowBroker(
            settings=ShadowBrokerSettings(
                ledger_path=tmp_path / "shadow.jsonl"
            ),
            now_provider=lambda: NOW,
        ),
        reporter=writer,
    )
    batch = execution_batch()

    first = service.replicate(batch)
    second = service.replicate(batch)
    payload = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert first.recorded_count == 1
    assert second.existing_count == 1
    assert payload["state"] == "consistent"
    assert payload["consistent"] is True
    assert payload["input_count"] == 1
    assert payload["replicated_count"] == 1
    assert payload["recorded_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["orders"][0]["code"] == "7203"


class FailingReporter:
    def record(self, result) -> None:
        del result
        raise OSError("report disk unavailable")


def test_report_failure_is_isolated_from_paper(tmp_path) -> None:
    service = PaperShadowReplicationService(
        shadow_recorder=ShadowBroker(
            settings=ShadowBrokerSettings(
                ledger_path=tmp_path / "shadow.jsonl"
            ),
            now_provider=lambda: NOW,
        ),
        reporter=FailingReporter(),
    )

    result = service.replicate(execution_batch())

    assert result.replicated_count == 1
    assert result.report_error == "report disk unavailable"
    assert result.is_consistent is False
