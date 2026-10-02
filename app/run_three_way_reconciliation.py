"""Paper、Shadow、実口座在庫のGET専用照合CLI。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TextIO

from app.live.three_way_reconciliation import (
    BrokerInventoryReader,
    PaperExecutionReader,
    ShadowLedgerReader,
    ThreeWayReconciliationReport,
    ThreeWayReconciliationReportWriter,
    ThreeWayReconciliationService,
    TOKYO,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.run_three_way_reconciliation"
    )
    parser.add_argument("--database-path", type=Path, default=Path("data/katana.db"))
    parser.add_argument(
        "--shadow-ledger",
        type=Path,
        default=Path("reports/live/shadow_orders.jsonl"),
    )
    parser.add_argument(
        "--broker-report",
        type=Path,
        default=Path("reports/live/kabu_station_read_only.json"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("reports/live/three_way_reconciliation.json"),
    )
    parser.add_argument("--trading-date")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
) -> int:
    arguments = build_argument_parser().parse_args(argv)
    trading_date = (
        datetime.strptime(arguments.trading_date, "%Y-%m-%d").date()
        if arguments.trading_date
        else datetime.now(TOKYO).date()
    )
    try:
        paper_orders = PaperExecutionReader(arguments.database_path).read(
            trading_date
        )
        shadow_orders = ShadowLedgerReader(arguments.shadow_ledger).read(
            trading_date
        )
        connected, active_order_ids, position_codes = BrokerInventoryReader(
            arguments.broker_report
        ).read()
        report = ThreeWayReconciliationService().reconcile(
            trading_date=trading_date,
            paper_orders=paper_orders,
            shadow_orders=shadow_orders,
            broker_snapshot_connected=connected,
            broker_active_order_ids=active_order_ids,
            broker_position_codes=position_codes,
        )
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(
            f"三者照合を実行できませんでした。 error={error}",
            file=output,
        )
        return 2
    ThreeWayReconciliationReportWriter(arguments.report_path).write(report)
    print_report(report, output=output)
    print(f"report={arguments.report_path}", file=output)
    return 0 if report.consistent else 1


def print_report(report: ThreeWayReconciliationReport, *, output: TextIO) -> None:
    print("Project KATANA Three-Way Reconciliation", file=output)
    print("=" * 48, file=output)
    print(f"trading_date={report.trading_date.isoformat()}", file=output)
    print(
        f"paper={report.paper_order_count} shadow={report.shadow_order_count} "
        f"matched={report.matched_order_count}",
        file=output,
    )
    print(
        f"broker_active_orders={report.broker_active_order_count} "
        f"broker_positions={report.broker_position_count}",
        file=output,
    )
    print(f"issues={report.issue_count}", file=output)
    print(f"result={'PASS' if report.consistent else 'BLOCKED'}", file=output)
    print("Live Trading: BLOCKED", file=output)


if __name__ == "__main__":
    raise SystemExit(run())
