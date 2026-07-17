"""Dashboard共通モデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardComponentError,
    DashboardOrderSummary,
)
from app.trading.order_models import OrderStatus


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def test_component_error_normalizes_values() -> None:
    error = DashboardComponentError(
        component=" portfolio ",
        error_message=" failed ",
    )

    assert error.component == "portfolio"
    assert error.error_message == "failed"


def test_order_summary_validates_status_counts() -> None:
    summary = DashboardOrderSummary(
        total_count=2,
        active_count=1,
        terminal_count=1,
        status_counts={
            OrderStatus.SENT: 1,
            OrderStatus.FILLED: 1,
        },
    )

    assert summary.status_counts[OrderStatus.SENT] == 1
    assert summary.status_counts[OrderStatus.NEW] == 0


def test_order_summary_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="一致しません"):
        DashboardOrderSummary(
            total_count=1,
            active_count=1,
            terminal_count=1,
            status_counts={
                OrderStatus.SENT: 1,
            },
        )


def test_broker_status_requires_message_when_disconnected() -> None:
    connected = DashboardBrokerStatus(
        connected=True,
        name="paper",
    )

    assert connected.message is None

    with pytest.raises(ValueError, match="メッセージ"):
        DashboardBrokerStatus(
            connected=False,
            name="paper",
        )
