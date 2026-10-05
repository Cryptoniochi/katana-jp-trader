from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.live.live_dry_run_operator_composition import (
    LiveDryRunOperatorComposition,
    LiveDryRunOperatorPaths,
)
from app.live.live_dry_run_operational_models import LiveDryRunAuditRecord
from app.trading.order_models import OrderSide, OrderType, TradeOrder

DRY_RUN_CONFIRMATION = "DRY-RUN"
# Step 6C-C compatibility: keep the safety-shell confirmation API available.
OPERATOR_CONFIRMATION = "RUN-LIVE-DRY-RUN"


def validate_operator_arguments(args: argparse.Namespace) -> date:
    """Validate the Step 6C-C safety-shell argument contract."""
    if args.confirm != OPERATOR_CONFIRMATION:
        raise SystemExit(
            f"--confirm must be exactly {OPERATOR_CONFIRMATION}."
        )

    trading_date = (
        args.trading_date
        if isinstance(args.trading_date, date)
        else date.fromisoformat(args.trading_date)
    )
    expected = f"KATANA-LIVE-{trading_date.isoformat()}"
    if args.live_confirmation != expected:
        raise SystemExit(
            f"--live-confirmation must be exactly {expected}."
        )

    if Path(args.database_path) == Path("data/katana.db"):
        raise SystemExit(
            "--database-path must not be data/katana.db."
        )

    return trading_date


@dataclass(frozen=True, slots=True)
class LiveDryRunOperatorRequest:
    trading_date: date
    order: TradeOrder
    idempotency_key: str
    confirmation: str

    def __post_init__(self) -> None:
        key = self.idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key must not be empty.")
        if self.confirmation != DRY_RUN_CONFIRMATION:
            raise ValueError("Operator confirmation must be exactly DRY-RUN.")
        object.__setattr__(self, "idempotency_key", key)


class LiveDryRunOperator:
    def __init__(self, *, service_provider) -> None:
        self.service_provider = service_provider

    def execute(self, request: LiveDryRunOperatorRequest) -> LiveDryRunAuditRecord:
        service = self.service_provider()
        from app.live.live_order_models import LiveOrderIntent

        intent = LiveOrderIntent(
            order=request.order,
            idempotency_key=request.idempotency_key,
            created_at=service.coordinator._current_time(),
        )
        return service.run(intent=intent, trading_date=request.trading_date)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one audited, network-free KATANA Live dry-run."
    )
    parser.add_argument("--trading-date", required=True, type=_date)
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--signal-id", required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--side", required=True, choices=("buy", "sell"))
    parser.add_argument(
        "--order-type",
        required=True,
        choices=("market", "limit", "stop", "stop_limit"),
    )
    parser.add_argument("--quantity", required=True, type=_positive_int)
    parser.add_argument("--limit-price", type=float)
    parser.add_argument("--stop-price", type=float)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--live-confirmation", required=True)
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/live_dry_run.db"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("reports/live/live_dry_run_audit.json"),
    )
    return parser


def request_from_args(args: argparse.Namespace) -> LiveDryRunOperatorRequest:
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
        trading_date=args.trading_date,
        order=order,
        idempotency_key=args.idempotency_key,
        confirmation=args.confirm,
    )


def validate_live_confirmation(trading_date: date, value: str) -> None:
    expected = f"KATANA-LIVE-{trading_date.isoformat()}"
    if value != expected:
        raise ValueError(f"Live confirmation must be exactly {expected}.")


def format_record(record: LiveDryRunAuditRecord) -> str:
    return "\n".join(
        (
            f"state={record.state.value}",
            f"trading_date={record.trading_date}",
            f"execution_key={record.execution_key}",
            f"order_id={record.order_id}",
            f"signal_id={record.signal_id}",
            f"readiness_activation_ready={str(record.readiness_activation_ready).lower()}",
            f"readiness_transport_ready={str(record.readiness_transport_ready).lower()}",
            f"readiness_live_order_ready={str(record.readiness_live_order_ready).lower()}",
            f"journal_state={record.journal_state}",
            f"simulated_broker_order_id={record.simulated_broker_order_id}",
            "broker_transmission_occurred=false",
            f"message={record.message}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = request_from_args(args)
    validate_live_confirmation(request.trading_date, args.live_confirmation)
    paths = LiveDryRunOperatorPaths(
        database_path=args.database_path,
        report_path=args.report_path,
    )
    bundle = LiveDryRunOperatorComposition.create_from_production_read_only(
        trading_date=request.trading_date,
        live_confirmation=args.live_confirmation,
        paths=paths,
    )
    operator = LiveDryRunOperator(service_provider=lambda: bundle.service)
    record = operator.execute(request)
    print(format_record(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
