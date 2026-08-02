"""Paper Trading Traceのテスト。"""

import json
from datetime import datetime, timezone

from app.dynamic_watchlist.strategy_routing_models import (
    SymbolStrategyRoute,
)
from app.market.symbol_strategy_router import (
    StrategyRouteDecision,
)
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

    recorder.strategy_route_resolved(
        signal,
        decision=StrategyRouteDecision(
            code="7203",
            strategy_names=("pullback",),
            routed=True,
            reason="Dynamic Watchlist preferred strategy.",
        ),
        route=SymbolStrategyRoute(
            code="7203",
            strategy_name="pullback",
            rating_tier="B",
            total_score=57.4,
            strategy_score=6.78,
        ),
    )
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
    assert snapshot.strategy_route_resolved_count == 1
    assert snapshot.routed_strategy_count == 1
    assert snapshot.fallback_strategy_count == 0
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
        "strategy_route_resolved",
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



def test_trace_records_fallback_route(tmp_path) -> None:
    path = tmp_path / "trace.jsonl"
    recorder = PaperTradingTraceRecorder(
        output_path=path
    )
    signal = make_signal()

    recorder.strategy_route_resolved(
        signal,
        decision=StrategyRouteDecision(
            code="7203",
            strategy_names=(
                "orb",
                "pullback",
                "high-breakout",
            ),
            routed=False,
            reason="No symbol-specific route.",
        ),
        route=None,
    )

    snapshot = recorder.snapshot()

    assert snapshot.strategy_route_resolved_count == 1
    assert snapshot.routed_strategy_count == 0
    assert snapshot.fallback_strategy_count == 1

    row = json.loads(
        path.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )
    assert row["event_type"] == "strategy_route_resolved"
    assert row["payload"]["route_source"] == "fallback"
    assert row["payload"]["rating_tier"] is None
