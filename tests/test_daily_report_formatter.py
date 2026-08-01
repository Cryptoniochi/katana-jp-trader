"""DailyReportNotificationFormatterのテスト。"""

from app.notifications.daily_report_formatter import (
    DailyReportNotificationFormatter,
)


def test_formatter_builds_complete_report_message() -> None:
    payload = {
        "available": True,
        "report_date": "2026-08-03",
        "status": "complete",
        "summary": {
            "trade_count": 4,
            "net_profit_loss": 1100.0,
            "win_rate": 0.5,
            "profit_factor": 3.75,
            "maximum_drawdown": -400.0,
        },
        "strategy_breakdown": [
            {
                "key": "orb",
                "label": "ORB",
                "net_profit_loss": 600.0,
            },
            {
                "key": "pullback",
                "label": "Pullback",
                "net_profit_loss": 500.0,
            },
        ],
        "symbol_breakdown": [
            {
                "key": "7203",
                "label": "7203",
                "net_profit_loss": 1500.0,
            }
        ],
        "error_count": 0,
        "recovery_count": 1,
        "notes": [],
    }

    content = (
        DailyReportNotificationFormatter()
        .format(payload)
    )

    assert "2026-08-03" in content.title
    assert "+1,100円" in content.body
    assert "50.0%" in content.body
    assert "3.75" in content.body
    assert "Best Strategy" in content.body
    assert "ORB" in content.body
    assert "Top Symbol" in content.body
    assert content.metadata[
        "net_profit_loss"
    ] == 1100.0


def test_formatter_handles_unavailable_report() -> None:
    content = (
        DailyReportNotificationFormatter()
        .format(
            {
                "available": False,
                "report_date": "2026-08-03",
                "status": "not_available",
                "message": (
                    "Daily trading report has not "
                    "been generated yet."
                ),
            }
        )
    )

    assert "not available" in content.body
    assert not content.metadata["available"]
