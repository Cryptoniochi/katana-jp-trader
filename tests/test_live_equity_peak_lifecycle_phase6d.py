"""Phase 6-D Step 1E tests for fail-closed live equity peak lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_equity_peak_observer import LiveEquityPeakObserver
from app.live.live_equity_peak_state import LiveEquityPeakStore


NOW = datetime(2026, 10, 4, 12, 30, tzinfo=timezone.utc)


def store(tmp_path):
    return LiveEquityPeakStore(
        tmp_path / "live_equity_peak.json",
        now_provider=lambda: NOW,
    )


def snapshot(*, cash=1_000_000.0):
    return KabuStationReadOnlySnapshot(
        generated_at=NOW,
        state="complete",
        connected=True,
        token_issued=True,
        cash_wallet={"StockAccountWallet": cash},
        margin_wallet={},
        positions=(),
        orders=(),
        errors=(),
    )


def test_observe_missing_state_fails_closed_without_creating_file(tmp_path):
    subject = store(tmp_path)

    with pytest.raises(RuntimeError):
        subject.observe(1_250_000.0)

    assert not subject.path.exists()


def test_initialize_creates_first_peak_explicitly(tmp_path):
    subject = store(tmp_path)

    state = subject.initialize(1_250_000.0)

    assert state.peak_equity == pytest.approx(1_250_000.0)
    assert subject.peak_equity() == pytest.approx(1_250_000.0)


def test_initialize_refuses_existing_valid_state(tmp_path):
    subject = store(tmp_path)
    subject.initialize(1_500_000.0)

    with pytest.raises(RuntimeError):
        subject.initialize(900_000.0)

    assert subject.peak_equity() == pytest.approx(1_500_000.0)


def test_initialize_refuses_existing_corrupt_state_without_overwrite(tmp_path):
    subject = store(tmp_path)
    subject.path.write_text("broken", encoding="utf-8")

    with pytest.raises(RuntimeError):
        subject.initialize(1_500_000.0)

    assert subject.path.read_text(encoding="utf-8") == "broken"


def test_observe_after_initialize_advances_but_never_reduces_peak(tmp_path):
    subject = store(tmp_path)
    subject.initialize(1_000_000.0)

    assert subject.observe(1_300_000.0).peak_equity == pytest.approx(1_300_000.0)
    assert subject.observe(1_100_000.0).peak_equity == pytest.approx(1_300_000.0)


def test_deleted_state_cannot_be_reinitialized_by_normal_observe(tmp_path):
    subject = store(tmp_path)
    subject.initialize(2_000_000.0)
    subject.path.unlink()

    with pytest.raises(RuntimeError):
        subject.observe(1_000_000.0)

    assert not subject.path.exists()


def test_observer_requires_explicit_initialization(tmp_path):
    peak_store = store(tmp_path)
    observer = LiveEquityPeakObserver(
        snapshot_provider=lambda: snapshot(cash=1_250_000.0),
        peak_store=peak_store,
    )

    with pytest.raises(RuntimeError):
        observer.observe()

    assert not peak_store.path.exists()


def test_observer_initialize_then_observe(tmp_path):
    peak_store = store(tmp_path)
    values = iter((1_250_000.0, 1_500_000.0))
    observer = LiveEquityPeakObserver(
        snapshot_provider=lambda: snapshot(cash=next(values)),
        peak_store=peak_store,
    )

    initialized = observer.initialize()
    observed = observer.observe()

    assert initialized.peak_equity == pytest.approx(1_250_000.0)
    assert observed.peak_equity == pytest.approx(1_500_000.0)


def test_observer_initialize_refuses_to_reset_existing_peak(tmp_path):
    peak_store = store(tmp_path)
    first = LiveEquityPeakObserver(
        snapshot_provider=lambda: snapshot(cash=2_000_000.0),
        peak_store=peak_store,
    )
    first.initialize()

    second = LiveEquityPeakObserver(
        snapshot_provider=lambda: snapshot(cash=1_000_000.0),
        peak_store=peak_store,
    )
    with pytest.raises(RuntimeError):
        second.initialize()

    assert peak_store.peak_equity() == pytest.approx(2_000_000.0)
