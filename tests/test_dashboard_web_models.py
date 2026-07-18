"""Dashboard Webモデルのテスト。"""

from datetime import date, datetime, timezone

from app.dashboard.dashboard_web_models import (
    DashboardDailyPoint,
    DashboardWebPayload,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_web_payload_is_json_compatible() -> None:
    payload = DashboardWebPayload(
        generated_at=NOW,
        snapshot={"complete": True},
        daily_history=(
            DashboardDailyPoint(
                trading_date=date(2026, 7, 18),
                net_profit_loss=10_000.0,
                final_equity=1_010_000.0,
                return_rate=0.01,
            ),
        ),
        cumulative_profit_loss=10_000.0,
    )

    value = payload.to_dict()

    assert value["generated_at"] == NOW.isoformat()
    assert value["cumulative_profit_loss"] == 10_000.0
    assert value["daily_history"][0][
        "trading_date"
    ] == "2026-07-18"
