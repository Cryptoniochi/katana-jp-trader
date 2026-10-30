from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_account_state_service import (
    KabuStationLiveAccountStateService,
    LiveAccountStateUnavailableError,
)


NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


def _snapshot(**overrides):
    values = dict(
        generated_at=NOW,
        state="complete",
        connected=True,
        token_issued=True,
        cash_wallet={"StockAccountWallet": 978_845.0},
        margin_wallet={},
        positions=(
            {
                "Symbol": "3911",
                "LeavesQty": 100,
                "Price": 212.0,
                "CurrentPrice": 210.0,
            },
        ),
        orders=(
            {"ID": "filled", "State": 5},
            {"ID": "working", "State": 2},
        ),
        errors=(),
    )
    values.update(overrides)
    return KabuStationReadOnlySnapshot(**values)


def test_complete_snapshot_becomes_authoritative_account_state():
    state = KabuStationLiveAccountStateService.from_snapshot(_snapshot())

    assert state.cash_balance == 978_845.0
    assert state.position_codes == frozenset({"3911"})
    assert state.total_exposure == 21_000.0
    assert state.positions[0].quantity == 100
    assert state.positions[0].average_price == 212.0
    assert len(state.active_orders) == 1
    assert state.active_orders[0]["ID"] == "working"


def test_partial_snapshot_fails_closed():
    with pytest.raises(LiveAccountStateUnavailableError):
        KabuStationLiveAccountStateService.from_snapshot(
            _snapshot(state="partial", connected=False, errors=("positions: timeout",))
        )


def test_missing_cash_wallet_fails_closed():
    with pytest.raises(LiveAccountStateUnavailableError):
        KabuStationLiveAccountStateService.from_snapshot(
            _snapshot(cash_wallet=None)
        )


def test_fully_closed_zero_quantity_position_is_ignored():
    state = KabuStationLiveAccountStateService.from_snapshot(
        _snapshot(
            positions=(
                {
                    "Symbol": "3911",
                    "LeavesQty": 0,
                    "HoldQty": 0,
                    "Price": 212.0,
                    "CurrentPrice": 210.0,
                },
            )
        )
    )

    assert state.positions == ()
    assert state.position_codes == frozenset()
    assert state.total_exposure == 0.0


def test_zero_leaves_with_positive_hold_quantity_fails_closed():
    with pytest.raises(
        LiveAccountStateUnavailableError,
        match="quantity is inconsistent",
    ):
        KabuStationLiveAccountStateService.from_snapshot(
            _snapshot(
                positions=(
                    {
                        "Symbol": "3911",
                        "LeavesQty": 0,
                        "HoldQty": 100,
                        "Price": 212.0,
                        "CurrentPrice": 210.0,
                    },
                )
            )
        )


def test_negative_position_quantity_still_fails_closed():
    with pytest.raises(LiveAccountStateUnavailableError):
        KabuStationLiveAccountStateService.from_snapshot(
            _snapshot(
                positions=(
                    {
                        "Symbol": "3911",
                        "LeavesQty": -1,
                        "HoldQty": 0,
                        "Price": 212.0,
                        "CurrentPrice": 210.0,
                    },
                )
            )
        )


def test_refresh_collects_once_and_persists_same_snapshot():
    snapshot = _snapshot(positions=())

    class Reader:
        def __init__(self):
            self.calls = 0

        def collect(self):
            self.calls += 1
            return snapshot

    class Writer:
        def __init__(self):
            self.seen = []

        def write(self, value):
            self.seen.append(value)
            return {}

    reader = Reader()
    writer = Writer()
    service = KabuStationLiveAccountStateService(
        read_only_service=reader,
        report_writer=writer,
    )

    state = service.refresh()

    assert reader.calls == 1
    assert writer.seen == [snapshot]
    assert state.position_codes == frozenset()
