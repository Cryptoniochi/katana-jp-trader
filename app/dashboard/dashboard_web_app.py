"""Project KATANA Read-only Web Dashboard。"""

from __future__ import annotations

from datetime import date

from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dashboard.dynamic_watchlist_status_reader import (
    DynamicWatchlistStatusReader,
)
from app.dashboard.morning_preflight_status_reader import (
    MorningPreflightStatusReader,
)
from app.dashboard.paper_trading_schedule_status_reader import (
    PaperTradingScheduleStatusReader,
)
from app.dashboard.katana_service_status_reader import (
    KatanaServiceStatusReader,
)
from app.dashboard.dashboard_strategy_service import (
    DashboardStrategyService,
)
from app.analytics.performance_breakdown_service import (
    PerformanceBreakdownAnalyzer,
)
from app.analytics.strategy_performance_service import (
    StrategyPerformanceAnalyzer,
)
from app.dashboard.dashboard_web_service import (
    DashboardWebService,
)
from app.dashboard.recovery_summary import RecoverySummary
from app.runtime.operational_readiness_service import (
    OperationalReadinessService,
)


PACKAGE_DIRECTORY = Path(__file__).resolve().parent
TEMPLATE_DIRECTORY = PACKAGE_DIRECTORY / "templates"
STATIC_DIRECTORY = PACKAGE_DIRECTORY / "static"


class RecoverySummaryProvider(Protocol):
    def build_summary(self) -> RecoverySummary:
        ...


def create_dashboard_app(
    *,
    service: DashboardWebService,
    recovery_service: RecoverySummaryProvider | None = None,
    strategy_service: DashboardStrategyService | None = None,
    performance_service: StrategyPerformanceAnalyzer | None = None,
    breakdown_service: PerformanceBreakdownAnalyzer | None = None,
    service_status_reader: KatanaServiceStatusReader | None = None,
    readiness_service: OperationalReadinessService | None = None,
    paper_schedule_reader: PaperTradingScheduleStatusReader | None = None,
    dynamic_watchlist_reader: DynamicWatchlistStatusReader | None = None,
    morning_preflight_reader: MorningPreflightStatusReader | None = None,
    daily_report_reader: DailyReportReader | None = None,
) -> FastAPI:
    """Read-only Dashboard用FastAPI Appを作成する。"""

    app = FastAPI(
        title="Project KATANA Dashboard",
        version="1.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    templates = Jinja2Templates(
        directory=str(TEMPLATE_DIRECTORY)
    )

    app.mount(
        "/static",
        StaticFiles(
            directory=str(STATIC_DIRECTORY)
        ),
        name="static",
    )

    @app.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def dashboard_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "page_title": (
                    "Project KATANA Dashboard"
                ),
            },
        )

    @app.get(
        "/mobile",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def mobile_dashboard_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="mobile_dashboard.html",
            context={
                "page_title": (
                    "Project KATANA Mobile"
                ),
            },
        )

    @app.get("/api/dashboard/summary")
    def dashboard_summary() -> dict:
        return service.create_payload().to_dict()

    @app.get("/api/dashboard/equity")
    def dashboard_equity() -> dict:
        payload = service.create_payload()
        return {
            "generated_at": (
                payload.generated_at.isoformat()
            ),
            "points": [
                point.to_dict()
                for point in payload.daily_history
            ],
        }

    @app.get("/api/dashboard/positions")
    def dashboard_positions() -> dict:
        payload = service.create_payload().to_dict()
        portfolio = payload["snapshot"].get(
            "portfolio"
        )
        return {
            "generated_at": payload["generated_at"],
            "positions": (
                portfolio.get("positions", [])
                if portfolio is not None
                else []
            ),
        }

    @app.get("/api/dashboard/recovery")
    def dashboard_recovery() -> dict[str, object]:
        summary = (
            recovery_service.build_summary()
            if recovery_service is not None
            else RecoverySummary()
        )
        return summary.to_dict()

    @app.get("/api/dashboard/dynamic-watchlist")
    def dashboard_dynamic_watchlist() -> dict[str, object]:
        if dynamic_watchlist_reader is None:
            return {
                "available": False,
                "generated_at": None,
                "schedule_state": "not_configured",
                "applied": False,
                "selected_count": 0,
                "evaluated_count": 0,
                "eligible_count": 0,
                "capital_limit": None,
                "purchase_budget": None,
                "message": (
                    "Dynamic Watchlist reader "
                    "is not configured."
                ),
                "candidates": [],
            }

        return dynamic_watchlist_reader.read()

    @app.get("/api/dashboard/morning-preflight")
    def dashboard_morning_preflight() -> dict[str, object]:
        if morning_preflight_reader is None:
            return {
                "available": False,
                "generated_at": None,
                "schedule_state": "not_configured",
                "overall_state": "unknown",
                "ready_for_trading": False,
                "target_date": None,
                "next_action_at": None,
                "last_attempt_at": None,
                "last_exit_code": None,
                "message": (
                    "Morning Pre-Flight reader "
                    "is not configured."
                ),
                "checks": [],
            }

        return morning_preflight_reader.read()

    @app.get("/api/dashboard/daily-report")
    def dashboard_daily_report(
        report_date: str | None = None,
    ) -> dict[str, object]:
        if daily_report_reader is None:
            return {
                "available": False,
                "source_path": None,
                "report_date": report_date,
                "generated_at": None,
                "status": "not_configured",
                "summary": {},
                "strategy_breakdown": [],
                "symbol_breakdown": [],
                "error_count": 0,
                "recovery_count": 0,
                "notes": [],
                "message": (
                    "Daily report reader is not configured."
                ),
            }

        if report_date is None:
            return daily_report_reader.read_latest()

        try:
            parsed_date = date.fromisoformat(
                report_date
            )
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=(
                    "report_date must use YYYY-MM-DD format."
                ),
            )

        return daily_report_reader.read_for_date(
            parsed_date
        )

    @app.get("/api/dashboard/paper-trading-schedule")
    def dashboard_paper_trading_schedule() -> dict[str, object]:
        if paper_schedule_reader is None:
            return {
                "available": False,
                "state": "not_configured",
                "enabled": False,
                "settings": {},
            }

        return paper_schedule_reader.read()

    @app.get("/api/dashboard/operational-readiness")
    def dashboard_operational_readiness() -> dict[str, object]:
        if readiness_service is None:
            return {
                "generated_at": None,
                "overall_state": "not_configured",
                "ready_for_paper_trading": False,
                "checks": [],
            }

        return readiness_service.evaluate().to_dict()

    @app.get("/api/dashboard/service-status")
    def dashboard_service_status() -> dict[str, object]:
        if service_status_reader is None:
            return {
                "available": False,
                "generated_at": None,
                "service_state": "not_configured",
                "kabu_station_readiness": "not_checked",
                "components": [],
                "message": (
                    "Service status reader is not configured."
                ),
            }

        return service_status_reader.read()

    @app.get("/api/dashboard/performance-breakdown")
    def dashboard_performance_breakdown() -> dict[str, object]:
        if breakdown_service is None:
            return {
                "generated_at": None,
                "weekday": [],
                "entry_hour": [],
                "symbol": [],
                "exit_reason": [],
            }

        return breakdown_service.analyze().to_dict()

    @app.get("/api/dashboard/performance")
    def dashboard_performance() -> dict[str, object]:
        if performance_service is None:
            return {
                "generated_at": None,
                "period_start": None,
                "period_end": None,
                "rankings": [],
            }

        return performance_service.analyze().to_dict()

    @app.get("/api/dashboard/strategies")
    def dashboard_strategies() -> dict[str, object]:
        if strategy_service is None:
            return {
                "generated_at": None,
                "trading_date": None,
                "strategies": [],
                "recent_trades": [],
                "recent_completed_trades": [],
            }

        return strategy_service.create_payload().to_dict()

    return app
