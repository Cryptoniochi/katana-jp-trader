from app.live.live_cancel_journal_repository import (
    LiveCancelJournalState,
    SQLiteLiveCancelJournalRepository,
)
from app.live.live_protective_cancel_service import (
    LiveCancelDecision,
    LiveProtectiveCancelService,
)


class Broker:
    def __init__(self, *, cancel_error=None, terminal=True):
        self.cancel_error = cancel_error
        self.terminal = terminal
        self.cancel_calls = 0

    def cancel_order(self, order_id):
        self.cancel_calls += 1
        if self.cancel_error:
            raise self.cancel_error
        return {"Result": 0, "OrderId": order_id}

    def orders(self, *, product=0):
        return (
            {
                "ID": "OID",
                "Symbol": "3911",
                "Side": "1",
                "State": 5 if self.terminal else 3,
                "LeavesQty": 0 if self.terminal else 100,
            },
        )


def service(tmp_path, broker):
    repo = SQLiteLiveCancelJournalRepository(tmp_path / "katana.db")
    return LiveProtectiveCancelService(
        client=broker, journal_repository=repo
    ), repo


def test_success_is_persisted_cancelled(tmp_path):
    broker = Broker()
    svc, repo = service(tmp_path, broker)
    result = svc.cancel_and_reconcile(broker_order_id="OID")
    assert result.decision is LiveCancelDecision.CANCELLED
    assert broker.cancel_calls == 1
    assert repo.get("OID").state is LiveCancelJournalState.CANCELLED


def test_ambiguous_cancel_is_persisted_unknown_and_not_retried_after_restart(tmp_path):
    db = tmp_path / "katana.db"
    broker = Broker(cancel_error=RuntimeError("timeout"))
    repo1 = SQLiteLiveCancelJournalRepository(db)
    svc1 = LiveProtectiveCancelService(client=broker, journal_repository=repo1)
    first = svc1.cancel_and_reconcile(broker_order_id="OID")
    assert first.decision is LiveCancelDecision.BLOCKED
    assert broker.cancel_calls == 1
    assert repo1.get("OID").state is LiveCancelJournalState.UNKNOWN

    repo2 = SQLiteLiveCancelJournalRepository(db)
    svc2 = LiveProtectiveCancelService(client=broker, journal_repository=repo2)
    second = svc2.cancel_and_reconcile(broker_order_id="OID")
    assert second.decision is LiveCancelDecision.CANCELLED
    # Restart recovery is read-only. cancel_order must never be sent twice.
    assert broker.cancel_calls == 1
    assert repo2.get("OID").state is LiveCancelJournalState.CANCELLED


def test_nonterminal_after_cancel_becomes_unknown_and_is_not_retried(tmp_path):
    broker = Broker(terminal=False)
    svc, repo = service(tmp_path, broker)
    first = svc.cancel_and_reconcile(broker_order_id="OID")
    assert first.decision is LiveCancelDecision.BLOCKED
    assert broker.cancel_calls == 1
    assert repo.get("OID").state is LiveCancelJournalState.UNKNOWN
    second = svc.cancel_and_reconcile(broker_order_id="OID")
    assert second.decision is LiveCancelDecision.BLOCKED
    assert broker.cancel_calls == 1


def test_existing_cancelled_record_does_not_resend_cancel(tmp_path):
    broker = Broker()
    svc, repo = service(tmp_path, broker)
    repo.begin_once("OID")
    repo.mark_cancelled("OID", "already done")
    result = svc.cancel_and_reconcile(broker_order_id="OID")
    assert result.decision is LiveCancelDecision.CANCELLED
    assert broker.cancel_calls == 0
