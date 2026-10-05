"""Audited operational wrapper for the network-free Step 6B E2E dry-run."""

import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.live.live_dry_run_e2e_coordinator import LiveDryRunE2ECoordinator
from app.live.live_dry_run_e2e_models import LiveDryRunE2EDecision
from app.live.live_dry_run_operational_models import (
    LiveDryRunAuditRecord,
    LiveDryRunAuditState,
)
from app.live.live_order_models import LiveOrderIntent


class LiveDryRunOperationalService:
    """Run Step 6B explicitly and persist non-transmitting audit evidence."""

    def __init__(self, *, coordinator: LiveDryRunE2ECoordinator, report_path: Path):
        self.coordinator = coordinator
        self.report_path = Path(report_path)

    def run(self, *, intent: LiveOrderIntent, trading_date: date) -> LiveDryRunAuditRecord:
        result = self.coordinator.run(intent=intent, trading_date=trading_date)
        items = tuple(
            {"key": x.key, "passed": x.passed, "message": x.message}
            for x in result.readiness_report.items
        )
        prep = result.preparation_result
        claim = result.claim_result
        sub = result.submission_result

        if sub is not None:
            journal_state = sub.journal_record.state.value
        elif claim is not None:
            journal_state = claim.journal_record.state.value
        elif prep is not None and prep.journal_record is not None:
            journal_state = prep.journal_record.state.value
        else:
            journal_state = None

        reached = (
            result.decision
            is LiveDryRunE2EDecision.SIMULATED_TRANSPORT_REACHED
        )
        record = LiveDryRunAuditRecord(
            schema_version=1,
            generated_at=result.evaluated_at,
            trading_date=trading_date.isoformat(),
            state=(
                LiveDryRunAuditState.SIMULATED_TRANSPORT_REACHED
                if reached else LiveDryRunAuditState.BLOCKED
            ),
            execution_key=intent.idempotency_key,
            order_id=intent.order.order_id,
            signal_id=intent.order.signal_id,
            readiness_activation_ready=result.readiness_report.activation_ready,
            readiness_transport_ready=result.readiness_report.transport_ready,
            readiness_live_order_ready=result.readiness_report.live_order_ready,
            readiness_items=items,
            preparation_decision=prep.decision.value if prep else None,
            claim_decision=claim.decision.value if claim else None,
            submission_decision=sub.decision.value if sub else None,
            journal_state=journal_state,
            simulated_broker_order_id=(
                sub.transport_result.simulated_broker_order_id if sub else None
            ),
            broker_transmission_occurred=False,
            message=result.message,
        )
        self._write(record)
        return record

    def _write(self, record: LiveDryRunAuditRecord) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        payload["generated_at"] = record.generated_at.isoformat()
        payload["state"] = record.state.value
        temporary = self.report_path.with_name(self.report_path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.report_path)
