"""MorningPreflightNotificationFormatterのテスト。"""

from app.notifications.morning_preflight_formatter import (
    MorningPreflightNotificationFormatter,
)


def test_formatter_builds_ready_message() -> None:
    content = (
        MorningPreflightNotificationFormatter()
        .format(
            {
                "overall_state": "ready",
                "ready_for_next_business_day": True,
                "checks": [
                    {
                        "key": "service",
                        "label": "KATANA Service",
                        "level": "pass",
                        "message": "healthy",
                    },
                    {
                        "key": "database",
                        "label": "Database",
                        "level": "pass",
                        "message": "exists",
                    },
                ],
            }
        )
    )

    assert "READY" in content.title
    assert "[OK] KATANA Service" in content.body
    assert "READY FOR TRADING" in content.body
    assert content.metadata[
        "failed_check_count"
    ] == 0


def test_formatter_lists_failed_reasons() -> None:
    content = (
        MorningPreflightNotificationFormatter()
        .format(
            {
                "overall_state": "blocked",
                "ready_for_next_business_day": False,
                "checks": [
                    {
                        "key": "watchlist",
                        "label": "Watchlist",
                        "level": "fail",
                        "message": "51 codes",
                    },
                ],
            }
        )
    )

    assert "NOT READY" in content.body
    assert "Reasons" in content.body
    assert "Watchlist: 51 codes" in content.body
