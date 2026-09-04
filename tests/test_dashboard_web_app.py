"""Read-only FastAPI Dashboardのテスト。"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.dashboard.dashboard_web_app import (
    create_dashboard_app,
)
from app.dashboard.dashboard_web_models import (
    DashboardWebPayload,
)
from app.dashboard.recovery_summary import (
    RecoveryStatus,
    RecoverySummary,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeService:
    """Dashboard Web Payloadを返すテスト用Service。"""

    def create_payload(self) -> DashboardWebPayload:
        return DashboardWebPayload(
            generated_at=NOW,
            snapshot={
                "complete": True,
                "partial": False,
                "portfolio": {
                    "positions": [],
                },
                "broker": {
                    "connected": True,
                    "name": "paper",
                    "message": None,
                },
            },
            daily_history=(),
            cumulative_profit_loss=0.0,
        )


class FakeRecoveryService:
    """RecoverySummaryを返すテスト用Service。"""

    def __init__(
        self,
        summary: RecoverySummary,
    ) -> None:
        self.summary = summary
        self.call_count = 0

    def build_summary(self) -> RecoverySummary:
        self.call_count += 1
        return self.summary


def create_test_client(
    *,
    recovery_service: FakeRecoveryService | None = None,
) -> TestClient:
    """テスト用Dashboard Clientを生成する。"""

    return TestClient(
        create_dashboard_app(
            service=FakeService(),
            recovery_service=recovery_service,
        )
    )


def test_dashboard_page_is_rendered() -> None:
    """Dashboard HTMLを取得できる。"""

    response = create_test_client().get("/")

    assert response.status_code == 200
    assert "PROJECT KATANA" in response.text
    assert "Trading Dashboard" in response.text
    assert "Today's P/L" in response.text


def test_summary_api_is_read_only_json() -> None:
    """Dashboard SummaryをJSONで取得できる。"""

    response = create_test_client().get(
        "/api/dashboard/summary"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["generated_at"] == NOW.isoformat()
    assert payload["snapshot"]["complete"] is True


def test_equity_and_positions_api() -> None:
    """EquityとPosition APIを取得できる。"""

    test_client = create_test_client()

    equity_response = test_client.get(
        "/api/dashboard/equity"
    )
    positions_response = test_client.get(
        "/api/dashboard/positions"
    )

    assert equity_response.status_code == 200
    assert equity_response.json()["points"] == []

    assert positions_response.status_code == 200
    assert positions_response.json()["positions"] == []


def test_recovery_api_returns_service_summary() -> None:
    """Recovery APIがServiceの集計結果を返す。"""

    summary = RecoverySummary(
        broker_attempts=2,
        broker_successes=1,
        broker_failures=1,
        last_broker_recovery=NOW,
        runtime_attempts=1,
        runtime_successes=1,
        runtime_failures=0,
        last_runtime_recovery=NOW,
        recovery_status=RecoveryStatus.FAILED,
        generated_at=NOW,
    )
    recovery_service = FakeRecoveryService(summary)

    response = create_test_client(
        recovery_service=recovery_service
    ).get("/api/dashboard/recovery")

    assert response.status_code == 200
    assert response.json() == summary.to_dict()
    assert recovery_service.call_count == 1


def test_recovery_api_returns_empty_summary_without_service() -> None:
    """Recovery Service未設定時は空の正常サマリーを返す。"""

    response = create_test_client().get(
        "/api/dashboard/recovery"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["broker"] == {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "last_recovery": None,
    }
    assert payload["runtime"] == {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "last_recovery": None,
    }
    assert payload["aggregate"] == {
        "total_attempts": 0,
        "total_successes": 0,
        "total_failures": 0,
        "success_rate": 100.0,
    }
    assert payload["recovery_status"] == "normal"
    assert payload["has_failure"] is False
    assert payload["is_healthy"] is True
    assert payload["generated_at"] is not None


def test_recovery_api_is_read_only() -> None:
    """Recovery APIへ書き込み系HTTPメソッドを使用できない。"""

    test_client = create_test_client()

    assert (
        test_client.post(
            "/api/dashboard/recovery"
        ).status_code
        == 405
    )
    assert (
        test_client.put(
            "/api/dashboard/recovery"
        ).status_code
        == 405
    )
    assert (
        test_client.delete(
            "/api/dashboard/recovery"
        ).status_code
        == 405
    )


def test_recovery_api_is_in_openapi_schema() -> None:
    """Recovery APIがOpenAPI Schemaへ公開される。"""

    response = create_test_client().get(
        "/openapi.json"
    )

    assert response.status_code == 200
    assert (
        "/api/dashboard/recovery"
        in response.json()["paths"]
    )


class FakePaperScheduleReader:
    def read(self) -> dict[str, object]:
        return {
            "available": True,
            "generated_at": NOW.isoformat(),
            "trading_date": "2026-07-18",
            "state": "running",
            "business_day": True,
            "enabled": True,
            "process_id": 4321,
            "last_exit_code": None,
            "next_action_at": (
                "2026-07-18T11:30:00+09:00"
            ),
            "message": (
                "run_market_session is active."
            ),
            "settings": {
                "start_at": "08:45",
                "morning_open_at": "09:00",
                "lunch_start_at": "11:30",
                "lunch_end_at": "12:30",
                "market_close_at": "15:30",
                "stop_at": "15:35",
            },
        }


def test_paper_trading_schedule_api_returns_runtime_state(
) -> None:
    client = TestClient(
        create_dashboard_app(
            service=FakeService(),
            paper_schedule_reader=(
                FakePaperScheduleReader()
            ),
        )
    )

    response = client.get(
        "/api/dashboard/paper-trading-schedule"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["enabled"] is True
    assert payload["process_id"] == 4321
    assert payload["trading_date"] == "2026-07-18"


def test_paper_trading_schedule_api_has_complete_fallback(
) -> None:
    response = create_test_client().get(
        "/api/dashboard/paper-trading-schedule"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "available": False,
        "generated_at": None,
        "trading_date": None,
        "state": "not_configured",
        "business_day": False,
        "enabled": False,
        "process_id": None,
        "last_exit_code": None,
        "next_action_at": None,
        "message": (
            "Paper Trading Schedule reader "
            "is not configured."
        ),
        "settings": {},
    }


def test_mobile_dashboard_contains_runtime_card(
) -> None:
    response = create_test_client().get("/mobile")

    assert response.status_code == 200
    assert "Runtime" in response.text
    assert 'id="mobile-runtime-state"' in response.text
    assert 'id="mobile-runtime-pid"' in response.text



class FakePaperRuntimeReader:
    def read(self) -> dict[str, object]:
        return {
            "available": True,
            "state": "running",
            "process_id": 4321,
            "cycle_count": 20,
            "signal_count": 3,
            "execution_count": 1,
        }


def test_paper_trading_runtime_api_returns_activity(
) -> None:
    client = TestClient(
        create_dashboard_app(
            service=FakeService(),
            paper_runtime_reader=FakePaperRuntimeReader(),
        )
    )

    response = client.get(
        "/api/dashboard/paper-trading-runtime"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["process_id"] == 4321
    assert payload["cycle_count"] == 20
    assert payload["signal_count"] == 3
    assert payload["execution_count"] == 1


def test_mobile_dashboard_contains_runtime_activity_fields(
) -> None:
    response = create_test_client().get("/mobile")

    assert response.status_code == 200
    assert 'id="mobile-runtime-cycles"' in response.text
    assert 'id="mobile-signals"' in response.text
    assert 'id="mobile-executions"' in response.text



def test_mobile_dashboard_uses_jst_datetime_formatting() -> None:
    response = create_test_client().get("/mobile")

    assert response.status_code == 200
    assert 'timeZone:"Asia/Tokyo"' in response.text
    assert "function formatJst" in response.text
    assert "function todayKey" in response.text


def test_mobile_dashboard_shows_only_today_executions() -> None:
    response = create_test_client().get("/mobile")

    assert response.status_code == 200
    assert "Today's Executions" in response.text
    assert "No executions today." in response.text
    assert "if(!t.executed_at)return false;" in response.text
    assert "===todayKey()" in response.text



def test_mobile_runtime_separates_pnl_and_labels_positions() -> None:
    response = create_test_client().get("/mobile")

    assert response.status_code == 200
    assert "Open Positions" in response.text
    assert "Realized P/L" in response.text
    assert "Unrealized P/L" in response.text
    assert 'id="mobile-realized"' in response.text
    assert 'id="mobile-unrealized"' in response.text
    assert 'id="mobile-position-list"' in response.text
    assert 'id="mobile-today-pl"' in response.text
