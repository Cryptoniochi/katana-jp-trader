from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.live_order_models import (
    LiveOrderBlockReason,
    LiveOrderBoundaryResult,
    LiveOrderDecision,
)
from app.live.live_prepared_execution_tracking_flow import (
    LivePreparedExecutionTrackingFlow,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 26, 0, 30, tzinfo=timezone.utc)


class BlockedPreparationService:
    def prepare(self, intent):
        return SimpleNamespace(
            is_prepared=False,
            boundary_result=LiveOrderBoundaryResult(
                intent=intent,
                decision=LiveOrderDecision.BLOCKED,
                reason=LiveOrderBlockReason.RECONCILIATION,
                evaluated_at=NOW,
                risk_assessment=None,
                kill_switch_evaluation=None,
                safety_snapshot=None,
                message="test reconciliation block",
            ),
        )


class NeverClaimGate:
    def claim(self, execution_key):
        raise AssertionError("claim must not run after blocked preparation")


class NeverTrackingFlow:
    def submit(self, **kwargs):
        raise AssertionError("submission must not run after blocked preparation")


def test_blocked_preparation_exposes_reason_and_message():
    flow = LivePreparedExecutionTrackingFlow(
        preparation_service=BlockedPreparationService(),
        claim_gate=NeverClaimGate(),
        tracking_flow=NeverTrackingFlow(),
        now_provider=lambda: NOW,
    )

    order = TradeOrder(
        order_id="diagnostic-order",
        signal_id="diagnostic-signal",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )

    with pytest.raises(RuntimeError) as exc_info:
        flow.submit(
            execution_key="diagnostic-execution",
            order=order,
            trading_date=date(2026, 10, 26),
        )

    message = str(exc_info.value)

    assert "reason=reconciliation" in message
    assert "message=test reconciliation block" in message
