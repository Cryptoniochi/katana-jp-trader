"""Phase 6-D Step 6C-B explicit operator CLI boundary for Live dry-run.

The CLI parser and executor are deliberately dependency-injected.  This module
does not construct Paper runtime, a broker client, or any network transport.
Production-state composition is a separate reviewed step.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.live.live_dry_run_operational_models import LiveDryRunAuditRecord
from app.live.live_dry_run_operational_service import LiveDryRunOperationalService
from app.live.live_order_models import LiveOrderIntent
from app.trading.order_models import OrderSide, OrderType, TradeOrder


DRY_RUN_CONFIRMATION = "DRY-RUN"
ServiceProvider = Callable[[], LiveDryRunOperationalService]
NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LiveDryRunOperatorRequest:
    trading_date: date
    order: TradeOrder
    idempotency_key: str
    confirmation: str

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty.")
        if self.confirmation != DRY_RUN_CONFIRMATION:
            raise ValueError(
                f"Exact confirmation {DRY_RUN_CONFIRMATION!r} is required."
            )


class LiveDryRunOperator:
    """Explicitly invoke the audited dry-run service after local confirmation."""

    def __init__(
        self,
        *,
        service_provider: ServiceProvider,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.service_provider = service_provider
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def execute(self, request: LiveDryRunOperatorRequest) -> LiveDryRunAuditRecord:
        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        intent = LiveOrderIntent(
            order=request.order,
            idempotency_key=request.idempotency_key,
            created_at=now.astimezone(timezone.utc),
        )
        return self.service_provider().run(
            intent=intent,
            trading_date=request.trading_date,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANA audited Live dry-run operator boundary. "
            "No production service is auto-connected in Step 6C-B."
        )
    )
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--side", required=True, choices=("buy", "sell"))
    parser.add_argument(
        "--order-type",
        required=True,
        choices=("market", "limit", "stop", "stop_limit"),
    )
    parser.add_argument("--quantity", required=True, type=int)
    parser.add_argument("--limit-price", type=float)
    parser.add_argument("--stop-price", type=float)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def parse_request(argv: Sequence[str]) -> LiveDryRunOperatorRequest:
    args = build_parser().parse_args(list(argv))
    try:
        trading_date = date.fromisoformat(args.trading_date)
    except ValueError as error:
        raise ValueError("trading-date must be YYYY-MM-DD.") from error

    order = TradeOrder(
        order_id=args.order_id,
        signal_id=args.signal_id,
        code=args.code,
        side=OrderSide(args.side),
        order_type=OrderType(args.order_type),
        quantity=args.quantity,
        limit_price=args.limit_price,
        stop_price=args.stop_price,
    )
    return LiveDryRunOperatorRequest(
        trading_date=trading_date,
        order=order,
        idempotency_key=args.idempotency_key,
        confirmation=args.confirm,
    )


def format_record(record: LiveDryRunAuditRecord) -> str:
    return "\n".join(
        (
            f"dry_run_state={record.state.value}",
            f"trading_date={record.trading_date}",
            f"execution_key={record.execution_key}",
            f"order_id={record.order_id}",
            f"signal_id={record.signal_id}",
            f"readiness_activation_ready={str(record.readiness_activation_ready).lower()}",
            f"readiness_transport_ready={str(record.readiness_transport_ready).lower()}",
            f"readiness_live_order_ready={str(record.readiness_live_order_ready).lower()}",
            f"journal_state={record.journal_state or 'none'}",
            f"simulated_broker_order_id={record.simulated_broker_order_id or 'none'}",
            "broker_transmission_occurred=false",
            f"message={record.message}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    # Fail closed by design. Step 6C-B establishes the operator command contract
    # only; Step 6C-C will connect it to reviewed production read-only state.
    _ = parse_request(argv if argv is not None else __import__("sys").argv[1:])
    raise SystemExit(
        "Step 6C-B operator CLI is not connected to production state. "
        "No dry-run was executed and no broker operation occurred."
    )


if __name__ == "__main__":
    raise SystemExit(main())
