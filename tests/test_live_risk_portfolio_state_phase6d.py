"""Phase 6-D Step 1A saved broker portfolio mapping tests."""
from datetime import datetime, timezone
import pytest
from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_risk_portfolio_state import KabuStationRiskPortfolioProvider
NOW=datetime(2026,10,4,10,0,tzinfo=timezone.utc)
def snap(cash=None,positions=(),state="complete",connected=True,token=True,errors=()):
    return KabuStationReadOnlySnapshot(NOW,state,connected,token,
        {"StockAccountWallet":1_000_000.0} if cash is None else cash,{},tuple(positions),(),tuple(errors))
def provider(s):
    return KabuStationRiskPortfolioProvider(snapshot_provider=lambda:s,
        daily_profit_loss_provider=lambda:-12500.0,
        consecutive_loss_count_provider=lambda:2,
        peak_equity_provider=lambda:1_300_000.0,now_provider=lambda:NOW)
def test_maps_saved_state():
    p=provider(snap(positions=({"Symbol":"7203","LeavesQty":100,"CurrentPrice":2500.0},
                               {"Symbol":"6758","LeavesQty":20,"CurrentPrice":5000.0})))()
    assert p.cash_balance==pytest.approx(1_000_000); assert p.total_exposure==pytest.approx(350_000)
    assert p.current_equity==pytest.approx(1_350_000); assert p.peak_equity==pytest.approx(1_350_000)
    assert p.open_position_codes==frozenset({"7203","6758"}); assert p.consecutive_losses==2
def test_fallback_fields():
    p=provider(snap(positions=({"Symbol":"9984","HoldQty":10,"Price":7000.0},)))()
    assert p.total_exposure==pytest.approx(70_000)
@pytest.mark.parametrize("s",[None,snap(state="partial"),snap(connected=False),snap(token=False),snap(errors=("x",))])
def test_unhealthy_fails_closed(s):
    with pytest.raises(RuntimeError): provider(s)()
@pytest.mark.parametrize("cash",[{},{"StockAccountWallet":None},{"StockAccountWallet":float("nan")},
                                  {"StockAccountWallet":float("inf")},{"StockAccountWallet":-1.0}])
def test_bad_cash_fails_closed(cash):
    with pytest.raises(RuntimeError): provider(snap(cash=cash))()
@pytest.mark.parametrize("pos",[
 {"Symbol":"","LeavesQty":1,"CurrentPrice":100.0},
 {"Symbol":"ABC","LeavesQty":1,"CurrentPrice":100.0},
 {"Symbol":"7203","CurrentPrice":100.0},
 {"Symbol":"7203","LeavesQty":1},
 {"Symbol":"7203","LeavesQty":-1,"CurrentPrice":100.0},
 {"Symbol":"7203","LeavesQty":1,"CurrentPrice":-100.0},
 {"Symbol":"7203","LeavesQty":float("nan"),"CurrentPrice":100.0}])
def test_bad_position_fails_closed(pos):
    with pytest.raises(RuntimeError): provider(snap(positions=(pos,)))()
def test_conflicting_fields_fail_closed():
    with pytest.raises(RuntimeError,match="ambiguous"):
        provider(snap(positions=({"Symbol":"7203","LeavesQty":100,"HoldQty":90,"CurrentPrice":2500.0},)))()
def test_no_network_or_order_methods():
    forbidden={"collect","issue_token","send","sendorder","submit","submit_order","cancel_order"}
    assert forbidden.isdisjoint(dir(KabuStationRiskPortfolioProvider))
