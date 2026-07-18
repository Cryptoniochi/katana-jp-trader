"""Project KATANA Web Dashboard Launcher。"""

from __future__ import annotations

import argparse
import threading
import webbrowser
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from app.dashboard.dashboard_snapshot_file import (
    DashboardJsonSnapshotReader,
)
from app.dashboard.dashboard_web_app import (
    create_dashboard_app,
)
from app.dashboard.dashboard_web_service import (
    DashboardWebService,
)
from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailySummaryRepository,
)
from app.runtime.recovery_history_repository import (
    RecoveryHistoryRepository,
)
from app.runtime.recovery_history_service import (
    RecoveryHistoryService,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DATABASE_PATH = Path("katana.db")
DEFAULT_SNAPSHOT_PATH = Path(
    "reports/dashboard/dashboard.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Dashboard Launcherの引数Parserを作成する。"""

    parser = argparse.ArgumentParser(
        prog="python -m app.dashboard",
        description=(
            "Project KATANA Read-only Web Dashboardを起動します。"
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"待受Host。既定値: {DEFAULT_HOST}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"待受Port。既定値: {DEFAULT_PORT}",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=(
            "Paper Trading日次履歴を読むSQLite Path。"
            f"既定値: {DEFAULT_DATABASE_PATH}"
        ),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help=(
            "最新Dashboard JSON Path。"
            f"既定値: {DEFAULT_SNAPSHOT_PATH}"
        ),
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=30,
        help="表示する日次履歴件数。既定値: 30",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="起動時にブラウザを自動で開きません。",
    )
    parser.add_argument(
        "--log-level",
        choices=(
            "critical",
            "error",
            "warning",
            "info",
            "debug",
            "trace",
        ),
        default="info",
        help="Uvicorn Log Level。既定値: info",
    )

    return parser


def create_recovery_history_service() -> RecoveryHistoryService:
    """Dashboard用Recovery履歴Serviceを構築する。"""

    repository = RecoveryHistoryRepository()

    return RecoveryHistoryService(
        repository=repository,
    )


def create_launcher_app(
    *,
    database_path: Path,
    snapshot_path: Path,
    history_limit: int,
    recovery_service: RecoveryHistoryService | None = None,
) -> FastAPI:
    """Launcher設定からFastAPI Appを構築する。"""

    snapshot_reader = DashboardJsonSnapshotReader(
        snapshot_path=snapshot_path
    )
    daily_repository = PaperTradingDailySummaryRepository(
        database_path,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    dashboard_service = DashboardWebService(
        snapshot_reader=snapshot_reader,
        daily_history_reader=daily_repository,
        history_limit=history_limit,
    )
    resolved_recovery_service = (
        recovery_service
        if recovery_service is not None
        else create_recovery_history_service()
    )

    return create_dashboard_app(
        service=dashboard_service,
        recovery_service=resolved_recovery_service,
    )


def dashboard_url(
    *,
    host: str,
    port: int,
) -> str:
    """ブラウザ表示用URLを返す。"""

    browser_host = (
        "127.0.0.1"
        if host in {"0.0.0.0", "::"}
        else host
    )
    return f"http://{browser_host}:{port}"


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Dashboardを起動する。"""

    args = build_parser().parse_args(argv)

    if not 1 <= args.port <= 65_535:
        raise ValueError(
            "Portは1以上65535以下で指定してください。"
        )

    if args.history_limit <= 0:
        raise ValueError(
            "日次履歴件数は0より大きい必要があります。"
        )

    app = create_launcher_app(
        database_path=args.database,
        snapshot_path=args.snapshot,
        history_limit=args.history_limit,
    )
    url = dashboard_url(
        host=args.host,
        port=args.port,
    )

    print("=" * 52)
    print("Project KATANA Dashboard")
    print(f"URL      : {url}")
    print(f"Database : {args.database}")
    print(f"Snapshot : {args.snapshot}")
    print("Recovery : in-memory history")
    print("Stop     : Ctrl+C")
    print("=" * 52)

    if not args.no_browser:
        timer = threading.Timer(
            1.0,
            webbrowser.open,
            args=(url,),
        )
        timer.daemon = True
        timer.start()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )

    return 0