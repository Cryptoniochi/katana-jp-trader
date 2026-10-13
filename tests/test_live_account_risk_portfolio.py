"""Tests for authoritative Live risk/position providers."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.live.live_account_risk_portfolio import (
    KabuStationLivePositionProvider,
    KabuStationLiveRiskPortfolioProvider,
)
from app.live.live_account_state_service import (
    LiveAccountState,
    LiveAccountStateUnavailableError,
    LiveCashPosition,
)


NOW = datetime(2026, 10, 13, 5, 0, tzinfo=timezone.utc)


class _AccountStateService:
    def __init__(self, state=None, error=None):
        self.state = state
        self.error = error
        self.calls = 0

    def refresh(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.state


def _state():
    return LiveAccountState(
        generated_at=NOW,
        cash_balance=700_000.0,
        positions=(
            LiveCashPosition(
                code="7203",
                quantity=100,
                average_price=2_000.0,
                current_price=2_100.0,
            ),
        ),
        orders=(),
    )


def _provider(service, *, peak=850_000.0, daily=-1_000.0, losses=1):
    return KabuStationLiveRiskPortfolioProvider(
        account_state_service=service,
        daily_profit_loss_provider=lambda: daily,
        consecutive_loss_count_provider=lambda: losses,
        peak_equity_provider=lambda: peak,
        now_provider=lambda: NOW,
    )


def test_risk_portfolio_uses_fresh_real_account_cash_exposure_and_codes():
    service = _AccountStateService(_state())
    snapshot = _provider(service)()

    assert service.calls == 1
    assert snapshot.cash_balance == 700_000.0
    assert snapshot.total_exposure == 210_000.0
    assert snapshot.current_equity == 910_000.0
    assert snapshot.peak_equity == 910_000.0
    assert snapshot.open_position_codes == frozenset({"7203"})
    assert snapshot.daily_realized_profit_loss == -1_000.0
    assert snapshot.consecutive_losses == 1
    assert snapshot.trading_date.isoformat() == "2026-10-13"


def test_risk_portfolio_refreshes_broker_on_every_call():
    service = _AccountStateService(_state())
    provider = _provider(service)

    provider()
    provider()

    assert service.calls == 2


def test_risk_portfolio_fails_closed_when_real_account_refresh_fails():
    service = _AccountStateService(
        error=LiveAccountStateUnavailableError("broker unavailable")
    )

    with pytest.raises(LiveAccountStateUnavailableError):
        _provider(service)()


def test_risk_portfolio_rejects_invalid_runtime_loss_state():
    service = _AccountStateService(_state())

    with pytest.raises(RuntimeError, match="daily realized"):
        _provider(service, daily=float("nan"))()


def test_position_provider_returns_real_positions_only():
    service = _AccountStateService(_state())
    positions = KabuStationLivePositionProvider(
        account_state_service=service
    )()

    assert service.calls == 1
    assert len(positions) == 1
    assert positions[0].code == "7203"
    assert positions[0].quantity == 100
