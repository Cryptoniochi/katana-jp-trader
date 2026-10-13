from app.live.live_exit_order_conflict_service import LiveExitOrderConflictDecision, LiveExitOrderConflictService

class Reader:
    def __init__(self,rows=(),error=None): self.rows=tuple(rows); self.error=error
    def orders(self,*,product=0):
        if self.error: raise self.error
        return self.rows
def check(rows=(),error=None):
    return LiveExitOrderConflictService(order_reader=Reader(rows,error)).check(code="3911")
def test_empty_clear(): assert check().is_clear
def test_terminal_clear(): assert check([{"ID":"x","Symbol":"3911","Side":"1","State":5,"LeavesQty":0}]).is_clear
def test_active_sell_blocks(): assert check([{"ID":"x","Symbol":"3911","Side":"1","State":3,"LeavesQty":100}]).decision is LiveExitOrderConflictDecision.BLOCKED
def test_active_buy_blocks(): assert check([{"ID":"x","Symbol":"3911","Side":"2","State":2,"LeavesQty":100}]).decision is LiveExitOrderConflictDecision.BLOCKED
def test_other_symbol_clear(): assert check([{"ID":"x","Symbol":"7203","Side":"1","State":3}]).is_clear
def test_read_failure_blocks(): assert check(error=RuntimeError("offline")).decision is LiveExitOrderConflictDecision.BLOCKED
def test_unknown_state_blocks(): assert check([{"ID":"x","Symbol":"3911","Side":"1","State":99}]).decision is LiveExitOrderConflictDecision.BLOCKED
def test_missing_id_blocks(): assert check([{"Symbol":"3911","Side":"1","State":3}]).decision is LiveExitOrderConflictDecision.BLOCKED
def test_no_cancel_or_send_methods():
    public={x.lower() for x in dir(LiveExitOrderConflictService) if not x.startswith("_")}
    assert {"cancel","cancel_order","send_order"}.isdisjoint(public)
