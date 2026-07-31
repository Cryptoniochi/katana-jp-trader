"""相場非依存のRisk Gate完全再現テスト。"""

from app.run_risk_gate_proof import (
    prove_daily_entry_limit,
    prove_daily_loss_limit,
    prove_duplicate_position_limit,
    prove_exit_allowed_after_loss,
    prove_order_value_limit,
)


def test_order_value_limit_blocks_before_broker() -> None:
    prove_order_value_limit()


def test_daily_loss_limit_blocks_before_broker() -> None:
    prove_daily_loss_limit()


def test_daily_entry_limit_blocks_second_entry() -> None:
    prove_daily_entry_limit()


def test_duplicate_position_blocks_before_broker() -> None:
    prove_duplicate_position_limit()


def test_exit_is_allowed_after_daily_loss() -> None:
    prove_exit_allowed_after_loss()
