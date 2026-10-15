from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.live.live_protective_exit_service import LiveProtectiveExitDecision
from app.live.live_protective_stop_cycle import LiveProtectiveStopCycle
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)

DAY = date(2026, 10, 16)


class LegacyPendingFlow:
    def __init__(self, decision):
        self.exit_service = self
        self.decision = decision
        self.submit_calls = 0

    def evaluate_stop_loss(self, **kwargs):
        return SimpleNamespace(decision=self.decision)

    def submit_stop_loss(self, **kwargs):
        self.submit_calls += 1
        raise AssertionError("legacy EXIT_PENDING must never resubmit")


def _legacy_pending(tmp_path: Path):
    repo = SQLiteLiveProtectiveStopRepository(tmp_path / "katana.db")
    repo.record_filled_entry(
        code="3911",
        entry_execution_key="legacy-entry",
        trading_date=DAY,
        quantity=100,
        fill_price=211.0,
    )
    row = repo.mark_exit_pending(entry_execution_key="legacy-entry")
    assert row.exit_execution_key is None
    assert row.exit_order_id is None
    return repo


def test_identity_less_legacy_pending_retires_when_authoritatively_flat(tmp_path):
    repo = _legacy_pending(tmp_path)
    result = LiveProtectiveStopCycle(
        repository=repo,
        execution_flow=LegacyPendingFlow(LiveProtectiveExitDecision.NO_POSITION),
    )(DAY)
    assert result.retired == 1
    assert result.blocked == 0
    assert repo.get_current("3911") is None


def test_identity_less_legacy_pending_blocks_if_position_still_exists(tmp_path):
    repo = _legacy_pending(tmp_path)
    flow = LegacyPendingFlow(LiveProtectiveExitDecision.EXIT_REQUIRED)
    result = LiveProtectiveStopCycle(repository=repo, execution_flow=flow)(DAY)
    assert result.submitted == 0
    assert result.blocked == 1
    assert flow.submit_calls == 0
    assert repo.get_current("3911").state is LiveProtectiveStopState.EXIT_PENDING
