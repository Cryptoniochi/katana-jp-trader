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
from app.dashboard.dashboard_strategy_service import (
    DashboardStrategyService,
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
DEFAULT_DATABASE_PATH = Path("data/katana.db")
DEFAULT_SNAPSHOT_PATH = Path(
    "reports/dashboard/dashboard.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.dashboard",
        description=(
            "Project KATANA Read-only Web Dashboardを起動します。"
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--recent-trade-limit",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
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
    )
    return parser


def create_recovery_history_service() -> RecoveryHistoryService:
    return RecoveryHistoryService(
        repository=RecoveryHistoryRepository(),
    )


def create_launcher_app(
    *,
    database_path: Path,
    snapshot_path: Path,
    history_limit: int,
    recent_trade_limit: int = 20,
    recovery_service: RecoveryHistoryService | None = None,
) -> FastAPI:
    snapshot_reader = DashboardJsonSnapshotReader(
        snapshot_path=snapshot_path
    )
    daily_repository = PaperTradingDailySummaryRepository(
        database_path,
        now_provider=lambda: datetime.now(
            timezone.utc
        ),
    )
    dashboard_service = DashboardWebService(
        snapshot_reader=snapshot_reader,
        daily_history_reader=daily_repository,
        history_limit=history_limit,
    )
    strategy_service = DashboardStrategyService(
        database_path,
        recent_trade_limit=recent_trade_limit,
    )

    return create_dashboard_app(
        service=dashboard_service,
        recovery_service=(
            recovery_service
            if recovery_service is not None
            else create_recovery_history_service()
        ),
        strategy_service=strategy_service,
    )


def dashboard_url(
    *,
    host: str,
    port: int,
) -> str:
    browser_host = (
        "127.0.0.1"
        if host in {"0.0.0.0", "::"}
        else host
    )
    return f"http://{browser_host}:{port}"


def mobile_dashboard_url(
    *,
    host: str,
    port: int,
) -> str:
    return (
        dashboard_url(
            host=host,
            port=port,
        )
        + "/mobile"
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    if not 1 <= args.port <= 65_535:
        raise ValueError(
            "Portは1以上65535以下で指定してください。"
        )

    if args.history_limit <= 0:
        raise ValueError(
            "日次履歴件数は0より大きい必要があります。"
        )

    if args.recent_trade_limit <= 0:
        raise ValueError(
            "最近約定件数は0より大きい必要があります。"
        )

    app = create_launcher_app(
        database_path=args.database,
        snapshot_path=args.snapshot,
        history_limit=args.history_limit,
        recent_trade_limit=(
            args.recent_trade_limit
        ),
    )
    url = dashboard_url(
        host=args.host,
        port=args.port,
    )
    mobile_url = mobile_dashboard_url(
        host=args.host,
        port=args.port,
    )

    print("=" * 52)
    print("Project KATANA Dashboard")
    print(f"Desktop  : {url}")
    print(f"Mobile   : {mobile_url}")
    print(f"Database : {args.database}")
    print(f"Snapshot : {args.snapshot}")
    print("Strategy : SQLite analytics")
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
