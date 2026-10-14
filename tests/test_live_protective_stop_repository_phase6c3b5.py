from datetime import date, datetime, timezone

import pytest

from app.live.live_protective_stop_repository import (
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)

DAY=date(2026,10,14)
NOW=datetime(2026,10,14,1,0,tzinfo=timezone.utc)


def repo(tmp_path):
    return SQLiteLiveProtectiveStopRepository(
        tmp_path/"katana.db", now_provider=lambda: NOW
    )


def test_confirmed_fill_creates_durable_one_percent_stop(tmp_path):
    r=repo(tmp_path)
    row=r.record_filled_entry(
        code="3911", entry_execution_key="entry-1", trading_date=DAY,
        quantity=100, fill_price=211.0,
    )
    assert row.stop_price == pytest.approx(208.89)
    assert row.state is LiveProtectiveStopState.ACTIVE
    reopened=SQLiteLiveProtectiveStopRepository(tmp_path/"katana.db")
    assert reopened.get_current("3911").entry_execution_key == "entry-1"


def test_same_confirmed_fill_is_idempotent(tmp_path):
    r=repo(tmp_path)
    kwargs=dict(code="3911", entry_execution_key="entry-1", trading_date=DAY,
                quantity=100, fill_price=211.0)
    assert r.record_filled_entry(**kwargs) == r.record_filled_entry(**kwargs)
    assert len(r.list_current()) == 1


def test_same_execution_key_with_different_fill_fails_closed(tmp_path):
    r=repo(tmp_path)
    r.record_filled_entry(code="3911", entry_execution_key="entry-1",
                          trading_date=DAY, quantity=100, fill_price=211.0)
    with pytest.raises(RuntimeError):
        r.record_filled_entry(code="3911", entry_execution_key="entry-1",
                              trading_date=DAY, quantity=100, fill_price=212.0)


def test_second_current_stop_for_same_symbol_is_rejected(tmp_path):
    r=repo(tmp_path)
    r.record_filled_entry(code="3911", entry_execution_key="entry-1",
                          trading_date=DAY, quantity=100, fill_price=211.0)
    with pytest.raises(RuntimeError):
        r.record_filled_entry(code="3911", entry_execution_key="entry-2",
                              trading_date=DAY, quantity=100, fill_price=220.0)


def test_pending_then_retired_allows_future_new_position(tmp_path):
    r=repo(tmp_path)
    r.record_filled_entry(code="3911", entry_execution_key="entry-1",
                          trading_date=DAY, quantity=100, fill_price=211.0)
    assert r.mark_exit_pending(entry_execution_key="entry-1").state is LiveProtectiveStopState.EXIT_PENDING
    assert r.retire(entry_execution_key="entry-1").state is LiveProtectiveStopState.RETIRED
    new=r.record_filled_entry(code="3911", entry_execution_key="entry-2",
                              trading_date=DAY, quantity=100, fill_price=220.0)
    assert new.state is LiveProtectiveStopState.ACTIVE
