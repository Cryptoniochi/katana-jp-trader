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

from app.analytics.performance_breakdown_service import (
    PerformanceBreakdownAnalyzer,
)
from app.analytics.strategy_performance_service import (
    StrategyPerformanceAnalyzer,
)
from app.dashboard.dynamic_watchlist_status_reader import (
    DynamicWatchlistStatusReader,
)
from app.dashboard.morning_preflight_status_reader import (
    MorningPreflightStatusReader,
)
from app.dashboard.universe_history_status_reader import (
    UniverseHistoryStatusReader,
)
from app.dashboard.paper_trading_schedule_status_reader import (
    PaperTradingScheduleStatusReader,
)
from app.dashboard.katana_service_status_reader import (
    KatanaServiceStatusReader,
)
from app.dashboard.daily_report_reader import (
    DailyReportReader,
)
from app.dashboard.dashboard_snapshot_file import (
    DashboardSqliteSnapshotReader,
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
from app.runtime.operational_readiness_service import (
    OperationalReadinessService,
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
DEFAULT_DYNAMIC_WATCHLIST_REPORT_PATH = Path(
    "reports/watchlist/latest.json"
)
DEFAULT_DYNAMIC_WATCHLIST_SCHEDULE_PATH = Path(
    "reports/service/dynamic_watchlist_schedule.json"
)
DEFAULT_MORNING_PREFLIGHT_STATUS_PATH = Path(
    "reports/service/morning_preflight_schedule.json"
)
DEFAULT_AUTONOMOUS_OPERATION_REPORT_PATH = Path(
    "reports/service/autonomous_operation_report.json"
)
DEFAULT_DAILY_REPORT_DIRECTORY = Path(
    "reports/daily"
)
DEFAULT_PAPER_SCHEDULE_STATUS_PATH = Path(
    "reports/service/paper_trading_schedule.json"
)
DEFAULT_SERVICE_STATUS_PATH = Path(
    "reports/service/katana_service_status.json"
)
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
        "--service-status",
        type=Path,
        default=DEFAULT_SERVICE_STATUS_PATH,
    )
    parser.add_argument(
        "--paper-schedule-status",
        type=Path,
        default=DEFAULT_PAPER_SCHEDULE_STATUS_PATH,
    )
    parser.add_argument(
        "--dynamic-watchlist-report",
        type=Path,
        default=DEFAULT_DYNAMIC_WATCHLIST_REPORT_PATH,
    )
    parser.add_argument(
        "--dynamic-watchlist-schedule",
        type=Path,
        default=DEFAULT_DYNAMIC_WATCHLIST_SCHEDULE_PATH,
    )
    parser.add_argument(
        "--morning-preflight-status",
        type=Path,
        default=DEFAULT_MORNING_PREFLIGHT_STATUS_PATH,
    )
    parser.add_argument(
        "--autonomous-operation-report",
        type=Path,
        default=DEFAULT_AUTONOMOUS_OPERATION_REPORT_PATH,
    )
    parser.add_argument(
        "--daily-report-directory",
        type=Path,
        default=DEFAULT_DAILY_REPORT_DIRECTORY,
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
    service_status_path: Path = DEFAULT_SERVICE_STATUS_PATH,
    paper_schedule_status_path: Path = (
        DEFAULT_PAPER_SCHEDULE_STATUS_PATH
    ),
    dynamic_watchlist_report_path: Path = (
        DEFAULT_DYNAMIC_WATCHLIST_REPORT_PATH
    ),
    dynamic_watchlist_schedule_path: Path = (
        DEFAULT_DYNAMIC_WATCHLIST_SCHEDULE_PATH
    ),
    morning_preflight_status_path: Path = (
        DEFAULT_MORNING_PREFLIGHT_STATUS_PATH
    ),
    autonomous_operation_report_path: Path = (
        DEFAULT_AUTONOMOUS_OPERATION_REPORT_PATH
    ),
    daily_report_directory: Path = (
        DEFAULT_DAILY_REPORT_DIRECTORY
    ),
    recovery_service: RecoveryHistoryService | None = None,
) -> FastAPI:
    snapshot_reader = DashboardSqliteSnapshotReader(
        database_path=database_path,
        snapshot_path=snapshot_path,
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
    performance_service = StrategyPerformanceAnalyzer(
        database_path
    )
    breakdown_service = PerformanceBreakdownAnalyzer(
        database_path
    )
    service_status_reader = KatanaServiceStatusReader(
        service_status_path
    )
    paper_schedule_reader = (
        PaperTradingScheduleStatusReader(
            paper_schedule_status_path
        )
    )
    dynamic_watchlist_reader = (
        DynamicWatchlistStatusReader(
            latest_report_path=(
                dynamic_watchlist_report_path
            ),
            schedule_status_path=(
                dynamic_watchlist_schedule_path
            ),
        )
    )
    morning_preflight_reader = (
        MorningPreflightStatusReader(
            schedule_status_path=(
                morning_preflight_status_path
            ),
            operation_report_path=(
                autonomous_operation_report_path
            ),
        )
    )
    daily_report_reader = DailyReportReader(
        daily_report_directory
    )
    universe_history_reader = UniverseHistoryStatusReader(
        database_path
    )
    readiness_service = OperationalReadinessService(
        database_path=database_path,
        watchlist_path=Path("watchlist.txt"),
        service_status_reader=service_status_reader,
        project_directory=Path.cwd(),
    )

    return create_dashboard_app(
        service=dashboard_service,
        recovery_service=(
            recovery_service
            if recovery_service is not None
            else create_recovery_history_service()
        ),
        strategy_service=strategy_service,
        performance_service=performance_service,
        breakdown_service=breakdown_service,
        service_status_reader=service_status_reader,
        readiness_service=readiness_service,
        paper_schedule_reader=paper_schedule_reader,
        dynamic_watchlist_reader=dynamic_watchlist_reader,
        morning_preflight_reader=morning_preflight_reader,
        daily_report_reader=daily_report_reader,
        universe_history_reader=universe_history_reader,
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
        service_status_path=args.service_status,
        paper_schedule_status_path=(
            args.paper_schedule_status
        ),
        dynamic_watchlist_report_path=(
            args.dynamic_watchlist_report
        ),
        dynamic_watchlist_schedule_path=(
            args.dynamic_watchlist_schedule
        ),
        morning_preflight_status_path=(
            args.morning_preflight_status
        ),
        autonomous_operation_report_path=(
            args.autonomous_operation_report
        ),
        daily_report_directory=(
            args.daily_report_directory
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
    print(f"Service  : {args.service_status}")
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
