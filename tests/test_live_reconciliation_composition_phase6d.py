"""Phase 6-D Step 2: saved three-way reconciliation composition tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.live.live_runtime_read_only_composition import (
    LiveRuntimeReadOnlyProviderFactory,
)


NOW = datetime(2026, 10, 4, 12, 30, tzinfo=timezone.utc)


class DailyRepo:
    def list_closed_trades(self, report_date):
        return ()


class Session:
    def snapshot(self):
        raise RuntimeError("must not be evaluated during construction")


def _write_reconciliation(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": NOW.isoformat(),
                "trading_date": "2026-10-04",
                "state": "consistent",
                "consistent": True,
                "paper_order_count": 0,
                "shadow_order_count": 0,
                "matched_order_count": 0,
                "paper_only_order_ids": [],
                "shadow_only_order_ids": [],
                "mismatches": [],
                "broker_snapshot_connected": True,
                "broker_active_order_count": 0,
                "broker_position_count": 0,
                "broker_active_order_ids": [],
                "broker_position_codes": [],
                "live_order_ready": False,
                "message": "read-only reconciliation",
            }
        ),
        encoding="utf-8",
    )


def _create(tmp_path: Path, reconciliation_path: Path | None):
    return LiveRuntimeReadOnlyProviderFactory.create(
        daily_trade_repository=DailyRepo(),
        runtime_session_service=Session(),
        kabu_station_report_path=tmp_path / "broker.json",
        live_equity_peak_path=tmp_path / "peak.json",
        three_way_reconciliation_report_path=reconciliation_path,
        now_provider=lambda: NOW,
    )


def test_factory_exposes_saved_three_way_reconciliation_provider(tmp_path):
    report_path = tmp_path / "three_way.json"
    _write_reconciliation(report_path)

    providers = _create(tmp_path, report_path)
    report = providers.reconciliation_report_provider()

    assert report is not None
    assert report.generated_at == NOW
    assert report.state == "consistent"
    assert report.consistent is True
    assert report.live_order_ready is False


def test_missing_saved_reconciliation_report_returns_none(tmp_path):
    providers = _create(tmp_path, tmp_path / "missing.json")
    assert providers.reconciliation_report_provider() is None


def test_omitted_reconciliation_path_preserves_fail_closed_compatibility(
    tmp_path,
):
    providers = LiveRuntimeReadOnlyProviderFactory.create(
        daily_trade_repository=DailyRepo(),
        runtime_session_service=Session(),
        kabu_station_report_path=tmp_path / "broker.json",
        live_equity_peak_path=tmp_path / "peak.json",
        now_provider=lambda: NOW,
    )
    assert providers.reconciliation_report_provider() is None


def test_corrupt_saved_reconciliation_report_raises(tmp_path):
    report_path = tmp_path / "three_way.json"
    report_path.write_text("{broken", encoding="utf-8")

    providers = _create(tmp_path, report_path)

    with pytest.raises((ValueError, json.JSONDecodeError)):
        providers.reconciliation_report_provider()


def test_factory_construction_does_not_read_reconciliation_file(tmp_path):
    report_path = tmp_path / "three_way.json"
    report_path.write_text("{broken", encoding="utf-8")

    providers = _create(tmp_path, report_path)

    assert providers.reconciliation_report_provider is not None


def test_step2_factory_has_no_live_execution_or_network_method():
    forbidden = {
        "collect",
        "issue_token",
        "send",
        "sendorder",
        "submit",
        "submit_order",
        "cancel_order",
    }
    assert forbidden.isdisjoint(dir(LiveRuntimeReadOnlyProviderFactory))
