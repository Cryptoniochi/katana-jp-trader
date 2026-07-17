"""Monitoring DashboardのCLI実行処理。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from app.dashboard.dashboard_exporter import (
    DashboardExportResult,
    DashboardExporter,
)
from app.dashboard.dashboard_formatter import (
    DashboardFormatter,
)
from app.dashboard.dashboard_models import DashboardSnapshot


class DashboardSnapshotProvider(Protocol):
    """Dashboard Snapshotを提供するインターフェース。"""

    def create_snapshot(self) -> DashboardSnapshot:
        """現在のDashboard Snapshotを返す。"""


@dataclass(frozen=True, slots=True)
class DashboardCliResult:
    """Dashboard CLIの実行結果。"""

    exit_code: int
    snapshot: DashboardSnapshot
    export_result: DashboardExportResult | None


def build_parser() -> argparse.ArgumentParser:
    """Dashboard CLIの引数Parserを作成する。"""

    parser = argparse.ArgumentParser(
        prog="katana-dashboard",
        description=(
            "Project KATANA Monitoring Dashboardを表示します。"
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help=(
            "Dashboard JSONの出力ディレクトリ。"
            "省略時はJSONを保存しません。"
        ),
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="タイムスタンプ付き履歴JSONを保存しません。",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="CLIテキストを表示せずJSONだけを保存します。",
    )
    parser.add_argument(
        "--fail-on-partial",
        action="store_true",
        help=(
            "一部コンポーネント取得失敗時に終了コード2を返します。"
        ),
    )

    return parser


def run_dashboard_cli(
    *,
    provider: DashboardSnapshotProvider,
    argv: Sequence[str] | None = None,
    output: TextIO,
    error_output: TextIO,
    formatter: DashboardFormatter | None = None,
) -> DashboardCliResult:
    """Dashboardを取得・表示・任意でJSON保存する。"""

    args = build_parser().parse_args(argv)
    resolved_formatter = formatter or DashboardFormatter()

    try:
        snapshot = provider.create_snapshot()
    except Exception as error:
        print(
            "Dashboard Snapshotを取得できませんでした。 "
            f"error={str(error).strip() or type(error).__name__}",
            file=error_output,
        )
        raise

    export_result: DashboardExportResult | None = None

    if args.json_output is not None:
        exporter = DashboardExporter(
            output_directory=args.json_output,
            save_history=not args.no_history,
        )

        try:
            export_result = exporter.export(snapshot)
        except Exception as error:
            print(
                "Dashboard JSONを保存できませんでした。 "
                f"error={str(error).strip() or type(error).__name__}",
                file=error_output,
            )
            raise

    if not args.json_only:
        print(
            resolved_formatter.format(snapshot),
            file=output,
        )

    exit_code = (
        2
        if args.fail_on_partial and snapshot.is_partial
        else 0
    )

    return DashboardCliResult(
        exit_code=exit_code,
        snapshot=snapshot,
        export_result=export_result,
    )
