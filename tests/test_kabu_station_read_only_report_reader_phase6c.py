"""Phase 6-C Step 4F-1 saved kabu Station report reader tests."""

import json
from datetime import datetime, timezone

import pytest

from app.live.kabu_station_read_only_report_reader import (
    KabuStationReadOnlyReportReader,
)


NOW = datetime(2026, 10, 3, 0, 30, tzinfo=timezone.utc)


def _payload():
    return {
        "generated_at": NOW.isoformat(),
        "state": "complete",
        "connected": True,
        "token_issued": True,
        "cash_wallet": {"StockAccountWallet": 1000000.0},
        "margin_wallet": None,
        "positions": [{"Symbol": "7203"}],
        "orders": [{"ID": "1", "State": 5}],
        "errors": [],
        "position_count": 1,
        "order_count": 1,
        "active_order_count": 0,
    }


def _write(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_missing_report_returns_none(tmp_path):
    reader = KabuStationReadOnlyReportReader(tmp_path / "missing.json")
    assert reader() is None


def test_reads_complete_snapshot_without_network_dependencies(tmp_path):
    path = tmp_path / "snapshot.json"
    _write(path, _payload())

    snapshot = KabuStationReadOnlyReportReader(path)()

    assert snapshot is not None
    assert snapshot.generated_at == NOW
    assert snapshot.state == "complete"
    assert snapshot.connected is True
    assert snapshot.token_issued is True
    assert snapshot.position_count == 1
    assert snapshot.order_count == 1
    assert snapshot.active_order_count == 0


def test_reader_ignores_derived_count_fields(tmp_path):
    path = tmp_path / "snapshot.json"
    payload = _payload()
    payload["position_count"] = 999
    payload["order_count"] = 999
    payload["active_order_count"] = 999
    _write(path, payload)

    snapshot = KabuStationReadOnlyReportReader(path)()

    assert snapshot.position_count == 1
    assert snapshot.order_count == 1
    assert snapshot.active_order_count == 0


def test_partial_snapshot_is_preserved_for_upper_fail_closed_gate(tmp_path):
    path = tmp_path / "snapshot.json"
    payload = _payload()
    payload["state"] = "partial"
    payload["connected"] = False
    payload["errors"] = ["positions: unavailable"]
    _write(path, payload)

    snapshot = KabuStationReadOnlyReportReader(path)()

    assert snapshot.state == "partial"
    assert snapshot.connected is False
    assert snapshot.errors == ("positions: unavailable",)


def test_naive_generated_at_is_rejected(tmp_path):
    path = tmp_path / "snapshot.json"
    payload = _payload()
    payload["generated_at"] = "2026-10-03T09:30:00"
    _write(path, payload)

    with pytest.raises(ValueError, match="timezone-aware"):
        KabuStationReadOnlyReportReader(path)()


def test_invalid_json_root_is_rejected(tmp_path):
    path = tmp_path / "snapshot.json"
    _write(path, [])

    with pytest.raises(ValueError, match="JSON object"):
        KabuStationReadOnlyReportReader(path)()


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("connected", "true", "boolean"),
        ("token_issued", 1, "boolean"),
        ("positions", {}, "list"),
        ("orders", [1], "only objects"),
        ("errors", "none", "list"),
        ("cash_wallet", [], "object or null"),
    ],
)
def test_malformed_fields_are_rejected(
    tmp_path,
    key,
    value,
    message,
):
    path = tmp_path / "snapshot.json"
    payload = _payload()
    payload[key] = value
    _write(path, payload)

    with pytest.raises(ValueError, match=message):
        KabuStationReadOnlyReportReader(path)()
