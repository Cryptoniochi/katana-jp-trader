from app.live.live_protective_cancel_service import LiveCancelDecision,LiveProtectiveCancelService
class C:
    def __init__(self,state=5,cancel_error=None,orders_error=None):self.state=state;self.cancel_error=cancel_error;self.orders_error=orders_error;self.calls=0
    def cancel_order(self,oid):
        self.calls+=1
        if self.cancel_error:raise self.cancel_error
        return {"Result":0,"OrderId":oid}
    def orders(self,*,product=0):
        if self.orders_error:raise self.orders_error
        return ({"ID":"OID","State":self.state},)
def test_cancel_terminal_ok():
    c=C();r=LiveProtectiveCancelService(client=c).cancel_and_reconcile(broker_order_id="OID");assert r.is_cancelled and c.calls==1
def test_ambiguous_cancel_never_retried():
    c=C(cancel_error=RuntimeError("timeout"));r=LiveProtectiveCancelService(client=c).cancel_and_reconcile(broker_order_id="OID");assert r.decision is LiveCancelDecision.BLOCKED and c.calls==1
def test_nonterminal_blocks():
    assert LiveProtectiveCancelService(client=C(state=4)).cancel_and_reconcile(broker_order_id="OID").decision is LiveCancelDecision.BLOCKED
def test_reconciliation_failure_blocks():
    assert LiveProtectiveCancelService(client=C(orders_error=RuntimeError("offline"))).cancel_and_reconcile(broker_order_id="OID").decision is LiveCancelDecision.BLOCKED
