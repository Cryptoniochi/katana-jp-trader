"""相場に依存せずPaper Trading Risk Gateを実証する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
)
from app.risk.paper_trading_pretrade_risk import (
    PaperTradingPreTradeRiskProvider,
    PaperTradingRiskDecision,
    PaperTradingRiskLimits,
)
from app.risk.risk_aware_queue_execution_service import (
    RiskAwareQueueExecutionService,
)
from app.trading.signal_models import SignalAction, TradeSignal


@dataclass(slots=True)
class FakeBroker:
    """Risk Provider向けの決定論的Broker状態。"""

    equity: float = 10_000_000.0
    cash_balance: float = 10_000_000.0
    positions: tuple[object, ...] = ()

    def get_account(self):
        return SimpleNamespace(
            equity=self.equity,
            cash_balance=self.cash_balance,
        )

    def list_positions(self):
        return list(self.positions)


class RecordingExecutionService:
    """Broker送信相当の呼出回数だけを記録する。"""

    def __init__(self) -> None:
        self.call_count = 0

    def execute_all(
        self,
        *,
        limit: int | None = None,
        continue_on_error: bool = True,
    ) -> BacktestQueueExecutionBatchResult:
        self.call_count += 1
        return BacktestQueueExecutionBatchResult(items=())


def make_signal(
    *,
    signal_id: str,
    code: str = "7203",
    action: SignalAction = SignalAction.BUY,
    quantity: int = 100,
    price: float = 2_500.0,
) -> TradeSignal:
    """検証用シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name="risk-proof",
        action=action,
        generated_at=datetime.now(timezone.utc),
        signal_price=price,
        quantity=quantity,
        reason="deterministic risk proof",
    )


def evaluate(
    *,
    provider: PaperTradingPreTradeRiskProvider,
    service: RiskAwareQueueExecutionService,
    delegate: RecordingExecutionService,
    signal: TradeSignal,
    current_price: float,
    expected_reason: str,
    expected_blocked: bool,
    expected_delegate_calls: int,
) -> PaperTradingRiskDecision:
    """1シナリオを評価し、下流呼出まで検証する。"""

    provider.prepare(signal, current_price)
    decision = provider()
    result = service.execute_all(risk_result=decision)

    assert decision.reason == expected_reason
    assert decision.is_blocked is expected_blocked
    assert result.was_blocked is expected_blocked
    assert delegate.call_count == expected_delegate_calls

    state = "BLOCKED" if decision.is_blocked else "ALLOWED"
    print(
        f"[PASS] {signal.signal_id}: "
        f"{state} reason={decision.reason} "
        f"broker_calls={delegate.call_count}"
    )
    return decision


def prove_order_value_limit() -> None:
    broker = FakeBroker()
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(
            max_position_value=100_000.0,
        ),
    )
    delegate = RecordingExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    evaluate(
        provider=provider,
        service=service,
        delegate=delegate,
        signal=make_signal(signal_id="order-value"),
        current_price=2_500.0,
        expected_reason="max_position_value_exceeded",
        expected_blocked=True,
        expected_delegate_calls=0,
    )


def prove_daily_loss_limit() -> None:
    broker = FakeBroker()
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(
            max_daily_loss=100_000.0,
        ),
    )
    broker.equity = 9_899_999.0

    delegate = RecordingExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    evaluate(
        provider=provider,
        service=service,
        delegate=delegate,
        signal=make_signal(signal_id="daily-loss"),
        current_price=2_500.0,
        expected_reason="max_daily_loss_reached",
        expected_blocked=True,
        expected_delegate_calls=0,
    )


def prove_daily_entry_limit() -> None:
    broker = FakeBroker()
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(
            max_daily_entries=1,
        ),
    )
    delegate = RecordingExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    evaluate(
        provider=provider,
        service=service,
        delegate=delegate,
        signal=make_signal(
            signal_id="entry-1",
            code="7203",
            quantity=10,
        ),
        current_price=2_500.0,
        expected_reason="entry_allowed",
        expected_blocked=False,
        expected_delegate_calls=1,
    )
    evaluate(
        provider=provider,
        service=service,
        delegate=delegate,
        signal=make_signal(
            signal_id="entry-2",
            code="9984",
            quantity=10,
        ),
        current_price=2_500.0,
        expected_reason="max_daily_entries_reached",
        expected_blocked=True,
        expected_delegate_calls=1,
    )


def prove_duplicate_position_limit() -> None:
    position = SimpleNamespace(
        code="7203",
        market_price=2_500.0,
        quantity=100,
    )
    broker = FakeBroker(positions=(position,))
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(),
    )
    delegate = RecordingExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    evaluate(
        provider=provider,
        service=service,
        delegate=delegate,
        signal=make_signal(signal_id="duplicate"),
        current_price=2_500.0,
        expected_reason="duplicate_symbol_position",
        expected_blocked=True,
        expected_delegate_calls=0,
    )


def prove_exit_allowed_after_loss() -> None:
    broker = FakeBroker()
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(
            max_daily_loss=100_000.0,
        ),
    )
    broker.equity = 9_800_000.0

    delegate = RecordingExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    evaluate(
        provider=provider,
        service=service,
        delegate=delegate,
        signal=make_signal(
            signal_id="exit-after-loss",
            action=SignalAction.EXIT,
        ),
        current_price=2_500.0,
        expected_reason="exit_order_allowed",
        expected_blocked=False,
        expected_delegate_calls=1,
    )


def main() -> int:
    """全リスクシナリオを順番に実証する。"""

    print("Project KATANA deterministic Risk Gate proof")
    print("No market connection. No live orders. No database writes.")
    print()

    scenarios = (
        ("order value limit", prove_order_value_limit),
        ("daily loss limit", prove_daily_loss_limit),
        ("daily entry limit", prove_daily_entry_limit),
        ("duplicate position limit", prove_duplicate_position_limit),
        ("exit after loss", prove_exit_allowed_after_loss),
    )

    for label, scenario in scenarios:
        print(f"--- {label} ---")
        scenario()

    print()
    print("ALL RISK GATE PROOFS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
