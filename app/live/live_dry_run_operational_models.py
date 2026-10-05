"""Phase 6-D Step 6C-A operational audit model for Live E2E dry-run."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LiveDryRunAuditState(StrEnum):
    BLOCKED = "blocked"
    SIMULATED_TRANSPORT_REACHED = "simulated_transport_reached"


@dataclass(frozen=True, slots=True)
class LiveDryRunAuditRecord:
    schema_version: int
    generated_at: datetime
    trading_date: str
    state: LiveDryRunAuditState
    execution_key: str
    order_id: str
    signal_id: str
    readiness_activation_ready: bool
    readiness_transport_ready: bool
    readiness_live_order_ready: bool
    readiness_items: tuple[dict[str, object], ...]
    preparation_decision: str | None
    claim_decision: str | None
    submission_decision: str | None
    journal_state: str | None
    simulated_broker_order_id: str | None
    broker_transmission_occurred: bool
    message: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported audit schema version.")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if self.broker_transmission_occurred:
            raise ValueError("Step 6C-A cannot record broker transmission.")
        if not self.execution_key.strip():
            raise ValueError("execution_key must not be empty.")
        if not self.order_id.strip() or not self.signal_id.strip():
            raise ValueError("order_id and signal_id must not be empty.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
