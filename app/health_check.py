"""Project KATANAの運用前Health Check CLI。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from app.market.market_calendar import TokyoMarketCalendar
from app.notifications.notification_composition import (
    NotificationComposition,
)
from app.run_paper_trading import (
    build_argument_parser as build_paper_argument_parser,
    create_production_settings,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
)
from app.runtime.production_readiness import (
    ProductionReadinessChecker,
    ProductionReadinessReport,
)
from app.settings import ROOT_DIR, Settings


def build_argument_parser() -> argparse.ArgumentParser:
    """Health Check固有のCLI引数を定義する。"""

    parser = argparse.ArgumentParser(
        prog="python -m app.health_check",
        description=(
            "Project KATANAの設定・DB・Runtime・通知構成を"
            "確認します。"
        ),
        add_help=True,
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT_DIR / ".env",
        help="設定を読み込む.envファイル",
    )

    return parser


def create_health_report(
    *,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    composition_factory=PaperTradingComposition,
) -> ProductionReadinessReport:
    """既存のProduction Readinessを使って診断する。"""

    parser = build_argument_parser()
    arguments, paper_arguments = (
        parser.parse_known_args(argv)
    )

    app_settings = Settings.from_environment(
        environment=environ,
        env_file=arguments.env_file,
    )
    notification_bundle = NotificationComposition.create(
        settings=app_settings.notifications,
        require_channel=False,
    )

    paper_parser = build_paper_argument_parser()
    paper_namespace = paper_parser.parse_args(
        paper_arguments
    )
    production_settings = create_production_settings(
        paper_namespace,
        environ=environ,
    )

    calendar = TokyoMarketCalendar()
    checker = ProductionReadinessChecker(
        composition_factory=composition_factory,
        notification_channel_provider=(
            lambda: notification_bundle.channel_names
        ),
        trading_day_provider=calendar.is_business_day,
    )

    return checker.check(
        settings=production_settings
    )


def print_health_report(
    report: ProductionReadinessReport,
    *,
    output: TextIO,
) -> None:
    """Health Check結果を表示する。"""

    print(
        "=========================================",
        file=output,
    )
    print(
        "Project KATANA Health Check",
        file=output,
    )
    print(
        "=========================================",
        file=output,
    )

    for item in report.items:
        marker = (
            "OK"
            if item.is_ok
            else "FAILED"
        )
        print(
            f"[{marker}] {item.name}",
            file=output,
        )
        print(
            f"       {item.message}",
            file=output,
        )

    print("", file=output)
    print("Overall", file=output)
    print(
        "READY"
        if report.is_ready
        else "NOT READY",
        file=output,
    )
    print(
        f"ok={report.ok_count} "
        f"failed={report.failure_count}",
        file=output,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
    composition_factory=PaperTradingComposition,
) -> int:
    """Health Checkを実行して終了コードを返す。"""

    try:
        report = create_health_report(
            argv=argv,
            environ=environ,
            composition_factory=composition_factory,
        )
        print_health_report(
            report,
            output=output,
        )
        return 0 if report.is_ready else 1

    except Exception as error:
        message = (
            str(error).strip()
            or type(error).__name__
        )
        print(
            "Health Checkを実行できませんでした。 "
            f"error={message}",
            file=error_output,
        )
        return 1


def main() -> None:
    """CLIエントリーポイント。"""

    raise SystemExit(run())


if __name__ == "__main__":
    main()
