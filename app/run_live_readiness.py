"""実注文を行わないLive Read-Only診断CLI。"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from app.live.execution_mode import ExecutionModeSettings
from app.live.kabu_station_read_only import (
    KabuStationReadOnlyReportWriter,
    KabuStationReadOnlyService,
)
from app.live.live_readiness import (
    LiveReadinessChecker,
    LiveReadinessReport,
    LiveReadinessReportWriter,
)
from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.settings import ROOT_DIR, load_env_file


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.run_live_readiness",
        description=(
            "kabuステーション実口座をGET APIだけで照会し、"
            "Live専用Readinessを生成します。"
        ),
    )
    parser.add_argument(
        "--env-file", type=Path, default=ROOT_DIR / ".env"
    )
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--read-only-report",
        type=Path,
        default=Path("reports/live/kabu_station_read_only.json"),
    )
    parser.add_argument(
        "--readiness-report",
        type=Path,
        default=Path("reports/live/live_readiness.json"),
    )
    parser.add_argument(
        "--shadow-report",
        type=Path,
        default=Path("reports/live/shadow_reconciliation.json"),
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output: TextIO = sys.stdout,
) -> int:
    arguments = build_argument_parser().parse_args(argv)
    values = load_env_file(arguments.env_file)
    values.update(dict(os.environ) if environ is None else dict(environ))
    password = (
        values.get("KABU_STATION_API_PASSWORD")
        or values.get("KABUSTATION_API_PASSWORD")
        or ""
    ).strip()
    if not password:
        print(
            "KABU_STATION_API_PASSWORDが設定されていません。",
            file=output,
        )
        return 2

    base_url = (
        arguments.base_url
        or values.get("KABU_STATION_BASE_URL")
        or "http://localhost:18080/kabusapi"
    )
    client = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password=password,
            base_url=base_url,
            timeout_seconds=arguments.timeout_seconds,
        )
    )
    snapshot = KabuStationReadOnlyService(client=client).collect()
    KabuStationReadOnlyReportWriter(
        arguments.read_only_report
    ).write(snapshot)
    report = LiveReadinessChecker().check(
        snapshot=snapshot,
        execution_settings=(
            ExecutionModeSettings.from_environment(values)
        ),
        shadow_report_path=arguments.shadow_report,
    )
    LiveReadinessReportWriter(arguments.readiness_report).write(report)
    print_report(report, output=output)
    print(f"read_only_report={arguments.read_only_report}", file=output)
    print(f"readiness_report={arguments.readiness_report}", file=output)
    return 0 if report.read_only_ready else 1


def print_report(
    report: LiveReadinessReport,
    *,
    output: TextIO,
) -> None:
    print("Project KATANA Live Readiness", file=output)
    print("=" * 42, file=output)
    for item in report.items:
        if item.key == "live_order_adapter":
            marker = "BLOCKED"
        else:
            marker = "PASS" if item.passed else "FAIL"
        print(f"[{marker}] {item.label}: {item.message}", file=output)
    print("", file=output)
    print(
        "Live Read-Only: "
        + ("READY" if report.read_only_ready else "NOT READY"),
        file=output,
    )
    print("Live Trading: BLOCKED", file=output)


if __name__ == "__main__":
    raise SystemExit(run())
