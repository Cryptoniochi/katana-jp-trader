from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from app.live.live_dry_run_operator_composition import LiveDryRunOperatorPaths

OPERATOR_CONFIRMATION = "RUN-LIVE-DRY-RUN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="KATANA operator Live dry-run safety shell; no real broker transmission."
    )
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--live-confirmation", required=True)
    parser.add_argument("--database-path", default=str(LiveDryRunOperatorPaths().database_path))
    parser.add_argument("--report-path", default=str(LiveDryRunOperatorPaths().report_path))
    return parser


def validate_operator_arguments(args: argparse.Namespace) -> date:
    if args.confirm != OPERATOR_CONFIRMATION:
        raise SystemExit(f"Operator confirmation must be exactly {OPERATOR_CONFIRMATION!r}.")
    trading_date = date.fromisoformat(args.trading_date)
    expected = f"KATANA-LIVE-{trading_date.isoformat()}"
    if args.live_confirmation != expected:
        raise SystemExit("Daily Live authorization token is invalid for the requested trading date.")
    if Path(args.database_path) == Path("data/katana.db"):
        raise SystemExit("Refusing to use production Paper database for dry-run.")
    LiveDryRunOperatorPaths(
        database_path=Path(args.database_path),
        report_path=Path(args.report_path),
    )
    return trading_date


def main() -> int:
    args = build_parser().parse_args()
    validate_operator_arguments(args)
    print(
        "Operator dry-run safety shell validated. "
        "Step 6C-C intentionally remains fail-closed until production read-only "
        "state providers are explicitly wired. No broker operation occurred."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
