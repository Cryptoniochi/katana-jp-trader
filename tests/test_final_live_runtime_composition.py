from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.final_live_runtime_composition import FinalLiveRuntimeFactory

NOW=datetime(2026,10,13,6,0,tzinfo=timezone.utc)

class NoNetworkClient:
    def __init__(self): self.calls=0
    def orders(self, *, product=0):
        self.calls += 1
        raise AssertionError("construction must not read broker")
    def positions(self, *, product=0, addinfo=True):
        self.calls += 1
        raise AssertionError("construction must not read broker")


def build(tmp_path):
    client=NoNetworkClient()
    bundle=FinalLiveRuntimeFactory.create(
        database_path=tmp_path/'live.db',
        kabu_client=client,
        sender=MagicMock(),
        execution_settings=ExecutionModeSettings(mode=TradingExecutionMode.LIVE),
        daily_trade_repository=MagicMock(),
        kabu_station_report_path=tmp_path/'account.json',
        live_equity_peak_path=tmp_path/'peak.json',
        risk_manager=MagicMock(),
        safety_snapshot_provider=MagicMock(),
        kill_switch_snapshot_provider=MagicMock(),
        market_price_provider=MagicMock(),
        now_provider=lambda:NOW,
    )
    return bundle,client


def test_final_live_runtime_constructs_without_broker_io(tmp_path):
    bundle,client=build(tmp_path)
    assert client.calls==0
    assert bundle.transport.activation_enabled is False
    assert bundle.transport.runtime_armed is False


def test_final_live_runtime_shares_one_submission_journal(tmp_path):
    bundle,_=build(tmp_path)
    assert bundle.submission_coordinator.journal is bundle.foundation.journal
    assert bundle.submitted_lifecycle.journal is bundle.foundation.journal


def test_final_live_runtime_uses_authoritative_account_for_position_consistency(tmp_path):
    bundle,_=build(tmp_path)
    assert (
        bundle.position_consistency_service.account_state_service
        is bundle.account.account_state_service
    )


def test_final_live_runtime_routes_protective_exit_through_prepared_tracking(tmp_path):
    bundle,_=build(tmp_path)
    assert (
        bundle.protective_exit_execution_flow.tracking_flow
        is bundle.prepared_tracking_flow
    )
    assert bundle.prepared_tracking_flow.tracking_flow is bundle.tracking_flow
    assert bundle.eod_liquidation_flow.execution_flow is bundle.protective_exit_execution_flow


def test_final_live_runtime_uses_durable_cancel_journal(tmp_path):
    bundle,_=build(tmp_path)
    assert bundle.cancel_service.journal_repository is bundle.cancel_journal
    assert bundle.conflict_resolver.cancel_service is bundle.cancel_service
