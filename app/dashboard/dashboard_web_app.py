"""Project KATANA Read-only Web Dashboard。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dashboard.dashboard_web_service import (
    DashboardWebService,
)


PACKAGE_DIRECTORY = Path(__file__).resolve().parent
TEMPLATE_DIRECTORY = PACKAGE_DIRECTORY / "templates"
STATIC_DIRECTORY = PACKAGE_DIRECTORY / "static"


def create_dashboard_app(
    *,
    service: DashboardWebService,
) -> FastAPI:
    """Read-only Dashboard用FastAPI Appを作成する。"""

    app = FastAPI(
        title="Project KATANA Dashboard",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )
    templates = Jinja2Templates(
        directory=str(TEMPLATE_DIRECTORY)
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIRECTORY)),
        name="static",
    )

    @app.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def dashboard_page(request: Request):
        """Dashboard v1のHTML画面を返す。"""

        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "page_title": "Project KATANA Dashboard",
            },
        )

    @app.get("/api/dashboard/summary")
    def dashboard_summary() -> dict:
        """現在状態と日次推移をJSONで返す。"""

        return service.create_payload().to_dict()

    @app.get("/api/dashboard/equity")
    def dashboard_equity() -> dict:
        """日次純資産推移だけをJSONで返す。"""

        payload = service.create_payload()
        return {
            "generated_at": payload.generated_at.isoformat(),
            "points": [
                point.to_dict()
                for point in payload.daily_history
            ],
        }

    @app.get("/api/dashboard/positions")
    def dashboard_positions() -> dict:
        """現在ポジションをJSONで返す。"""

        payload = service.create_payload().to_dict()
        portfolio = payload["snapshot"].get("portfolio")
        return {
            "generated_at": payload["generated_at"],
            "positions": (
                portfolio.get("positions", [])
                if portfolio is not None
                else []
            ),
        }

    return app
