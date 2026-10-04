"""Phase 6-D Step 1C tests for saved live equity observation."""

from datetime import datetime, timezone
import pytest

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_equity_peak_state import LiveEquityPeakStore
from app.live.live_equity_peak_observer import LiveEquityPeakObserver
from app.live.live_saved_equity import KabuStationSavedEquityCalculator

NOW=datetime(2026,10,4,12,0,tzinfo=timezone.utc)

def snapshot(*,cash=1_000_000.0,positions=(),state="complete",errors=()):
    return KabuStationReadOnlySnapshot(
        generated_at=NOW,state=state,connected=True,token_issued=True,
        cash_wallet={"StockAccountWallet":cash},margin_wallet={},
        positions=tuple(positions),orders=(),errors=tuple(errors))

def test_calculates_saved_live_equity():
    result=KabuStationSavedEquityCalculator()(snapshot(positions=(
        {"Symbol":"7203","LeavesQty":100,"CurrentPrice":2500.0},
        {"Symbol":"6758","HoldQty":20,"Price":5000.0},
    )))
    cash,exposure,equity,codes=result
    assert cash==pytest.approx(1_000_000)
    assert exposure==pytest.approx(350_000)
    assert equity==pytest.approx(1_350_000)
    assert codes==frozenset({"7203","6758"})

def test_observer_initializes_peak_from_saved_live_equity(tmp_path):
    store=LiveEquityPeakStore(tmp_path/"peak.json",now_provider=lambda:NOW)
    observer=LiveEquityPeakObserver(
        snapshot_provider=lambda:snapshot(positions=(
            {"Symbol":"7203","LeavesQty":100,"CurrentPrice":2500.0},
        )),peak_store=store)
    state=observer.initialize()
    assert state.peak_equity==pytest.approx(1_250_000)

def test_observer_never_reduces_peak(tmp_path):
    path=tmp_path/"peak.json"
    store=LiveEquityPeakStore(path,now_provider=lambda:NOW)
    LiveEquityPeakObserver(snapshot_provider=lambda:snapshot(cash=2_000_000),peak_store=store).initialize()
    LiveEquityPeakObserver(snapshot_provider=lambda:snapshot(cash=1_000_000),peak_store=store).observe()
    assert store.peak_equity()==pytest.approx(2_000_000)

@pytest.mark.parametrize("bad",[
    None,
    snapshot(state="partial"),
    snapshot(errors=("positions: failed",)),
    snapshot(cash=float("nan")),
])
def test_invalid_saved_snapshot_does_not_update_peak(tmp_path,bad):
    path=tmp_path/"peak.json"
    store=LiveEquityPeakStore(path,now_provider=lambda:NOW)
    with pytest.raises(RuntimeError):
        LiveEquityPeakObserver(snapshot_provider=lambda:bad,peak_store=store).initialize()
    assert not path.exists()

def test_corrupt_existing_peak_is_not_overwritten(tmp_path):
    path=tmp_path/"peak.json"; path.write_text("broken",encoding="utf-8")
    store=LiveEquityPeakStore(path,now_provider=lambda:NOW)
    with pytest.raises(RuntimeError):
        LiveEquityPeakObserver(snapshot_provider=lambda:snapshot(),peak_store=store).observe()
    assert path.read_text(encoding="utf-8")=="broken"

def test_components_expose_no_network_or_order_methods():
    forbidden={"collect","issue_token","send","sendorder","submit","submit_order","cancel_order"}
    assert forbidden.isdisjoint(dir(KabuStationSavedEquityCalculator))
    assert forbidden.isdisjoint(dir(LiveEquityPeakObserver))
