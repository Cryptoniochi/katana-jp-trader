from app.live.live_cancel_journal_repository import (
    LiveCancelJournalState,
    SQLiteLiveCancelJournalRepository,
)


def test_begin_once_is_durable_across_repository_restart(tmp_path):
    db = tmp_path / "katana.db"
    first = SQLiteLiveCancelJournalRepository(db)
    record, created = first.begin_once("OID-1")
    assert created
    assert record.state is LiveCancelJournalState.CANCEL_PENDING

    restarted = SQLiteLiveCancelJournalRepository(db)
    record2, created2 = restarted.begin_once("OID-1")
    assert not created2
    assert record2.state is LiveCancelJournalState.CANCEL_PENDING


def test_unknown_is_terminal_for_automatic_retry(tmp_path):
    repo = SQLiteLiveCancelJournalRepository(tmp_path / "katana.db")
    repo.begin_once("OID-2")
    repo.mark_unknown("OID-2", "timeout")
    record, created = repo.begin_once("OID-2")
    assert not created
    assert record.state is LiveCancelJournalState.UNKNOWN


def test_cancelled_is_durable(tmp_path):
    repo = SQLiteLiveCancelJournalRepository(tmp_path / "katana.db")
    repo.begin_once("OID-3")
    repo.mark_cancelled("OID-3", "done")
    restarted = SQLiteLiveCancelJournalRepository(tmp_path / "katana.db")
    record = restarted.get("OID-3")
    assert record is not None
    assert record.state is LiveCancelJournalState.CANCELLED
