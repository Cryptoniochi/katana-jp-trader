"""Project KATANA Read-only Web Dashboard。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dashboard.dashboard_strategy_service import (
    DashboardStrategyService,
)
from app.dashboard.dashboard_web_service import (
    DashboardWebService,
)
from app.dashboard.recovery_summary import RecoverySummary


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

    @app.get("/api/dashboard/strategies")
    def dashboard_strategies() -> dict[str, object]:
        if strategy_service is None:
            return {
                "generated_at": None,
                "trading_date": None,
                "strategies": [],
                "recent_trades": [],
            }

        return strategy_service.create_payload().to_dict()

    return app
