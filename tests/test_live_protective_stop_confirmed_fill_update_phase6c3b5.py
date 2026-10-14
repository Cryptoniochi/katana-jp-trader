from datetime import date

import pytest

from app.live.live_protective_stop_repository import SQLiteLiveProtectiveStopRepository

DAY=date(2026,10,14)


def test_confirmed_cumulative_fill_update_is_monotonic(tmp_path):
    r=SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")
    first=r.synchronize_confirmed_entry_fill(
        code="3911", entry_execution_key="e1", trading_date=DAY,
        cumulative_quantity=40, average_fill_price=210.0)
    assert first.quantity == 40
    second=r.synchronize_confirmed_entry_fill(
        code="3911", entry_execution_key="e1", trading_date=DAY,
        cumulative_quantity=100, average_fill_price=211.2)
    assert second.quantity == 100
    assert second.stop_price == pytest.approx(209.088)
    with pytest.raises(RuntimeError):
        r.synchronize_confirmed_entry_fill(
            code="3911", entry_execution_key="e1", trading_date=DAY,
            cumulative_quantity=90, average_fill_price=211.0)


def test_same_quantity_different_average_price_fails_closed(tmp_path):
    r=SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")
    r.synchronize_confirmed_entry_fill(
        code="3911", entry_execution_key="e1", trading_date=DAY,
        cumulative_quantity=40, average_fill_price=210.0)
    with pytest.raises(RuntimeError):
        r.synchronize_confirmed_entry_fill(
            code="3911", entry_execution_key="e1", trading_date=DAY,
            cumulative_quantity=40, average_fill_price=211.0)
