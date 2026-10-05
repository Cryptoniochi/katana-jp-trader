"""Phase 6-D Step 6C-A operational audit tests."""

import inspect
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.final_live_readiness import (
    FinalLiveReadinessItem,
    FinalLiveReadinessReport,
    FinalLiveReadinessState,
)
from app.live.live_dry_run_e2e_models import LiveDryRunE2EDecision, LiveDryRunE2EResult
from app.live.live_dry_run_operational_models import (
    LiveDryRunAuditRecord,
    LiveDryRunAuditState,
)
from app.live.live_dry_run_operational_service import LiveDryRunOperationalService

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 5)


def _intent():
    return SimpleNamespace(
        idempotency_key="dry-key",
        order=SimpleNamespace(order_id="order-1", signal_id="signal-1"),
    )


def _readiness(ready=True):
    return FinalLiveReadinessReport(
        generated_at=NOW,
        trading_date=DAY,
        activation_ready=ready,
        transport_ready=False,
        live_order_ready=False,
        state=FinalLiveReadinessState.ACTIVATION_READY if ready else FinalLiveReadinessState.BLOCKED,
        items=(FinalLiveReadinessItem("manual_kill_switch", ready, "ready" if ready else "blocked"),),
    )


class CoordinatorStub:
    def __init__(self, result):
        self.result = result
    def run(self, *, intent, trading_date):
        return self.result


def test_success_report_is_persisted_without_broker_transmission(tmp_path):
    sub = SimpleNamespace(
        decision=SimpleNamespace(value="simulated_transport_reached"),
        journal_record=SimpleNamespace(state=SimpleNamespace(value="submission_pending")),
        transport_result=SimpleNamespace(simulated_broker_order_id="DRYRUN-abc"),
    )
    result = LiveDryRunE2EResult(
        decision=LiveDryRunE2EDecision.SIMULATED_TRANSPORT_REACHED,
        evaluated_at=NOW,
        readiness_report=_readiness(),
        preparation_result=SimpleNamespace(
            decision=SimpleNamespace(value="prepared"),
            journal_record=SimpleNamespace(state=SimpleNamespace(value="prepared")),
        ),
        claim_result=SimpleNamespace(
            decision=SimpleNamespace(value="claimed"),
            journal_record=SimpleNamespace(state=SimpleNamespace(value="claimed")),
        ),
        submission_result=sub,
        message="simulated",
    )
    path = tmp_path / "audit.json"
    record = LiveDryRunOperationalService(
        coordinator=CoordinatorStub(result), report_path=path
    ).run(intent=_intent(), trading_date=DAY)

    assert record.state is LiveDryRunAuditState.SIMULATED_TRANSPORT_REACHED
    assert record.journal_state == "submission_pending"
    assert record.broker_transmission_occurred is False
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["broker_transmission_occurred"] is False
    assert payload["readiness_transport_ready"] is False
    assert payload["readiness_live_order_ready"] is False


def test_blocked_readiness_report_has_no_downstream_state(tmp_path):
    result = LiveDryRunE2EResult(
        decision=LiveDryRunE2EDecision.BLOCKED_READINESS,
        evaluated_at=NOW,
        readiness_report=_readiness(False),
        preparation_result=None,
        claim_result=None,
        submission_result=None,
        message="blocked",
    )
    record = LiveDryRunOperationalService(
        coordinator=CoordinatorStub(result), report_path=tmp_path / "audit.json"
    ).run(intent=_intent(), trading_date=DAY)
    assert record.state is LiveDryRunAuditState.BLOCKED
    assert record.journal_state is None
    assert record.simulated_broker_order_id is None


def test_audit_record_rejects_real_transmission_claim():
    with pytest.raises(ValueError):
        LiveDryRunAuditRecord(
            1, NOW, DAY.isoformat(), LiveDryRunAuditState.BLOCKED,
            "key", "order", "signal", False, False, False, (),
            None, None, None, None, None, True, "invalid",
        )


def test_operational_service_contains_no_network_or_submit_primitive():
    source = inspect.getsource(LiveDryRunOperationalService)
    for token in (
        "requests.", "httpx.", "urllib.", "KabuStationClient",
        "BrokerAdapter", "mark_submitted", ".post(", ".put(", ".request(",
    ):
        assert token not in source
