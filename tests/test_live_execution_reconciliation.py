from app.live.live_execution_reconciliation import (
    LiveExecutionReconciliationService,
    LiveExecutionReconciliationState,
)


class FakeClient:
    def __init__(self, orders=(), error=None):
        self._orders = tuple(orders)
        self.error = error
        self.calls = []

    def orders(self, *, product=0):
        self.calls.append(product)
        if self.error:
            raise self.error
        return self._orders


def order(*, oid="OID", qty=100, cum=0, state=1, details=None):
    return {"ID": oid, "OrderQty": qty, "CumQty": cum, "OrderState": state, "Details": details or []}


def test_accepted_is_not_treated_as_fill():
    client = FakeClient([order()])
    result = LiveExecutionReconciliationService(client=client).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.ACCEPTED
    assert result.cumulative_quantity == 0
    assert not result.is_terminal
    assert result.may_retry_submission is False
    assert client.calls == [1]


def test_partial_fill_is_distinct_from_full_fill():
    result = LiveExecutionReconciliationService(client=FakeClient([order(cum=40)])).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.PARTIALLY_FILLED
    assert result.remaining_quantity == 60


def test_real_style_filled_response_extracts_execution():
    details = [{"RecType": 8, "Price": 211, "Qty": 100, "ExecutionID": "E20261013056RD"}]
    result = LiveExecutionReconciliationService(client=FakeClient([order(cum=100, state=5, details=details)])).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.FILLED
    assert result.is_terminal
    assert result.fills[0].execution_id == "E20261013056RD"
    assert result.fills[0].price == 211


def test_terminal_zero_fill_is_not_fill():
    result = LiveExecutionReconciliationService(client=FakeClient([order(cum=0, state=5)])).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.TERMINATED_UNFILLED
    assert result.is_terminal


def test_terminal_partial_is_preserved():
    result = LiveExecutionReconciliationService(client=FakeClient([order(cum=25, state=5)])).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.TERMINATED_PARTIAL
    assert result.cumulative_quantity == 25
    assert result.remaining_quantity == 75


def test_missing_order_is_unknown_and_never_retry_permission():
    result = LiveExecutionReconciliationService(client=FakeClient([])).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.UNKNOWN
    assert result.may_retry_submission is False


def test_network_read_failure_is_fail_closed_unknown():
    result = LiveExecutionReconciliationService(client=FakeClient(error=TimeoutError())).reconcile("OID")
    assert result.state is LiveExecutionReconciliationState.UNKNOWN
    assert "TimeoutError" in result.detail
    assert result.may_retry_submission is False


def test_invalid_or_ambiguous_broker_data_is_unknown():
    duplicate = FakeClient([order(), order()])
    assert LiveExecutionReconciliationService(client=duplicate).reconcile("OID").state is LiveExecutionReconciliationState.UNKNOWN
    bad = FakeClient([order(qty=100, cum=101)])
    assert LiveExecutionReconciliationService(client=bad).reconcile("OID").state is LiveExecutionReconciliationState.UNKNOWN
