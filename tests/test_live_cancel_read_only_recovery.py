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
        self.cancel_error=cancel_error
        self.terminal=terminal
        self.cancel_calls=0
        self.order_reads=0

    def cancel_order(self, order_id):
        self.cancel_calls += 1
        if self.cancel_error:
            raise self.cancel_error
        return {"Result":0,"OrderId":order_id}

    def orders(self, *, product=0):
        self.order_reads += 1
        return ({
            "ID":"OID","Symbol":"3911","Side":"1",
            "State":5 if self.terminal else 3,
            "LeavesQty":0 if self.terminal else 100,
        },)


def make(tmp_path, broker):
    repo=SQLiteLiveCancelJournalRepository(tmp_path/"katana.db")
    return LiveProtectiveCancelService(
        client=broker, journal_repository=repo
    ),repo


def test_unknown_restart_recovers_from_terminal_broker_without_resending_cancel(tmp_path):
    db=tmp_path/"katana.db"
    first_broker=Broker(cancel_error=RuntimeError("timeout"))
    repo1=SQLiteLiveCancelJournalRepository(db)
    first=LiveProtectiveCancelService(
        client=first_broker,journal_repository=repo1
    ).cancel_and_reconcile(broker_order_id="OID")
    assert first.decision is LiveCancelDecision.BLOCKED
    assert first_broker.cancel_calls==1
    assert repo1.get("OID").state is LiveCancelJournalState.UNKNOWN

    recovery_broker=Broker(terminal=True)
    repo2=SQLiteLiveCancelJournalRepository(db)
    recovered=LiveProtectiveCancelService(
        client=recovery_broker,journal_repository=repo2
    ).cancel_and_reconcile(broker_order_id="OID")
    assert recovered.decision is LiveCancelDecision.CANCELLED
    assert recovery_broker.cancel_calls==0
    assert recovery_broker.order_reads==1
    assert repo2.get("OID").state is LiveCancelJournalState.CANCELLED


def test_pending_restart_recovers_from_terminal_broker_without_resending_cancel(tmp_path):
    broker=Broker(terminal=True)
    svc,repo=make(tmp_path,broker)
    repo.begin_once("OID")
    result=svc.cancel_and_reconcile(broker_order_id="OID")
    assert result.decision is LiveCancelDecision.CANCELLED
    assert broker.cancel_calls==0
    assert broker.order_reads==1
    assert repo.get("OID").state is LiveCancelJournalState.CANCELLED


def test_unknown_nonterminal_stays_blocked_and_never_resends_cancel(tmp_path):
    broker=Broker(terminal=False)
    svc,repo=make(tmp_path,broker)
    repo.begin_once("OID")
    repo.mark_unknown("OID","old timeout")
    result=svc.cancel_and_reconcile(broker_order_id="OID")
    assert result.decision is LiveCancelDecision.BLOCKED
    assert broker.cancel_calls==0
    assert broker.order_reads==1
    assert repo.get("OID").state is LiveCancelJournalState.UNKNOWN


def test_unknown_missing_order_stays_blocked_and_never_resends_cancel(tmp_path):
    class MissingBroker(Broker):
        def orders(self, *, product=0):
            self.order_reads += 1
            return ()
    broker=MissingBroker()
    svc,repo=make(tmp_path,broker)
    repo.begin_once("OID")
    repo.mark_unknown("OID","old timeout")
    result=svc.cancel_and_reconcile(broker_order_id="OID")
    assert result.decision is LiveCancelDecision.BLOCKED
    assert broker.cancel_calls==0
    assert repo.get("OID").state is LiveCancelJournalState.UNKNOWN
