"""Phase 6-D Step 1B tests for persistent live equity peak state."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.live.live_equity_peak_state import LiveEquityPeakStore


NOW = datetime(2026, 10, 4, 11, 30, tzinfo=timezone.utc)


def store(tmp_path):
    return LiveEquityPeakStore(
        tmp_path / "live_equity_peak.json",
        now_provider=lambda: NOW,
    )


def test_missing_state_fails_closed(tmp_path):
    with pytest.raises(RuntimeError):
        store(tmp_path).peak_equity()


def test_first_observation_initializes_peak(tmp_path):
    subject = store(tmp_path)
    state = subject.initialize(1_250_000.0)

    assert state.peak_equity == pytest.approx(1_250_000.0)
    assert subject.peak_equity() == pytest.approx(1_250_000.0)


def test_higher_observation_advances_peak(tmp_path):
    subject = store(tmp_path)
    subject.initialize(1_000_000.0)
    state = subject.observe(1_300_000.0)

    assert state.peak_equity == pytest.approx(1_300_000.0)


def test_lower_observation_never_reduces_peak(tmp_path):
    subject = store(tmp_path)
    subject.initialize(1_300_000.0)
    state = subject.observe(1_100_000.0)

    assert state.peak_equity == pytest.approx(1_300_000.0)


def test_persisted_state_is_readable_by_new_store_instance(tmp_path):
    first = store(tmp_path)
    first.initialize(1_234_567.0)

    second = store(tmp_path)
    assert second.peak_equity() == pytest.approx(1_234_567.0)


@pytest.mark.parametrize(
    "value",
    [None, True, "abc", -1.0, float("nan"), float("inf")],
)
def test_invalid_observation_fails_closed(tmp_path, value):
    with pytest.raises(RuntimeError):
        store(tmp_path).initialize(value)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"updated_at":"2026-10-04T11:30:00+00:00"}',
        '{"peak_equity":1000}',
        '{"peak_equity":-1,"updated_at":"2026-10-04T11:30:00+00:00"}',
        '{"peak_equity":"NaN","updated_at":"2026-10-04T11:30:00+00:00"}',
        '{"peak_equity":1000,"updated_at":"2026-10-04T11:30:00"}',
    ],
)
def test_corrupt_or_invalid_existing_state_fails_closed(tmp_path, payload):
    path = tmp_path / "live_equity_peak.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(RuntimeError):
        LiveEquityPeakStore(path).read()


def test_corrupt_existing_state_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "live_equity_peak.json"
    path.write_text("broken", encoding="utf-8")
    subject = LiveEquityPeakStore(path, now_provider=lambda: NOW)

    with pytest.raises(RuntimeError):
        subject.observe(2_000_000.0)

    assert path.read_text(encoding="utf-8") == "broken"


def test_written_payload_contains_only_live_peak_state(tmp_path):
    subject = store(tmp_path)
    subject.initialize(1_500_000.0)

    payload = json.loads(subject.path.read_text(encoding="utf-8"))
    assert set(payload) == {"peak_equity", "updated_at"}
    assert payload["peak_equity"] == pytest.approx(1_500_000.0)


def test_store_exposes_no_broker_network_or_order_methods():
    forbidden = {
        "collect",
        "issue_token",
        "send",
        "sendorder",
        "submit",
        "submit_order",
        "cancel_order",
    }
    assert forbidden.isdisjoint(dir(LiveEquityPeakStore))
