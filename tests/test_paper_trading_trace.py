"""Paper Trading Traceのテスト。"""

import json
from datetime import datetime, timezone

from app.risk.paper_trading_pretrade_risk import (
    PaperTradingRiskDecision,
)
from app.risk.paper_trading_trace import (
    PaperTradingTraceRecorder,
)
from app.trading.signal_models import SignalAction, TradeSignal


def make_signal() -> TradeSignal:
    return TradeSignal(
        signal_id="signal-1",
        code="7203",
        strategy_name="test",
        action=SignalAction.BUY,
        generated_at=datetime.now(timezone.utc),
        signal_price=2500.0,
        quantity=100,
        reason="test",
    )


def test_trace_records_full_blocked_path(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    recorder = PaperTradingTraceRecorder(
        output_path=path
    )
    signal = make_signal()

    recorder.signal_generated(signal, 2500.0)
    recorder.queue_enqueued(
        signal,
        was_enqueued=True,
    )
    recorder.risk_evaluated(
        signal,
        PaperTradingRiskDecision(
            allows_new_entries=False,
            is_blocked=True,
            reason="max_daily_loss_reached",
            daily_profit_loss=-100001.0,
            position_count=0,
            total_exposure=0.0,
            cash_balance=9899999.0,
            proposed_order_value=250000.0,
            daily_entry_count=0,
        ),
    )
    recorder.broker_result(
        signal,
        executed=False,
        saved_execution_count=0,
        blocked_reason="max_daily_loss_reached",
    )

    snapshot = recorder.snapshot()
    assert snapshot.signal_generated_count == 1
    assert snapshot.queue_enqueued_count == 1
    assert snapshot.risk_evaluated_count == 1
    assert snapshot.risk_blocked_count == 1
    assert snapshot.broker_skipped_count == 1
    assert snapshot.broker_executed_count == 0

    rows = [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [row["event_type"] for row in rows] == [
        "signal_generated",
        "queue_enqueued",
        "risk_evaluated",
        "broker_skipped",
    ]


def test_trace_records_allowed_execution() -> None:
    recorder = PaperTradingTraceRecorder()
    signal = make_signal()

    recorder.signal_generated(signal, 2500.0)
    recorder.risk_evaluated(
        signal,
        PaperTradingRiskDecision(
            allows_new_entries=True,
            is_blocked=False,
            reason="entry_allowed",
            daily_profit_loss=0.0,
            position_count=0,
            total_exposure=0.0,
            cash_balance=10000000.0,
            proposed_order_value=250000.0,
            daily_entry_count=1,
        ),
    )
    recorder.broker_result(
        signal,
        executed=True,
        saved_execution_count=1,
    )

    snapshot = recorder.snapshot()
    assert snapshot.risk_allowed_count == 1
    assert snapshot.broker_executed_count == 1
    assert snapshot.broker_skipped_count == 0
