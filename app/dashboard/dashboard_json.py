"""DashboardSnapshotをJSON互換データへ変換する。"""

from __future__ import annotations

from typing import Any

from app.dashboard.dashboard_models import DashboardSnapshot
from app.runtime.resource_report import (
    runtime_resource_evaluation_to_dict,
)
from app.runtime.runtime_health_monitor_report import (
    runtime_health_monitor_report_to_dict,
)


def dashboard_snapshot_to_dict(
    snapshot: DashboardSnapshot,
) -> dict[str, Any]:
    """機密情報を含まないJSON互換辞書へ変換する。"""

    system_health = snapshot.system_health
    runtime_metrics = snapshot.runtime_metrics
    portfolio = snapshot.portfolio
    orders = snapshot.orders
    live_summary = snapshot.live_summary
    broker = snapshot.broker
    runtime_resource = snapshot.runtime_resource
    runtime_health = snapshot.runtime_health

    return {
        "generated_at": snapshot.generated_at.isoformat(),
        "complete": snapshot.is_complete,
        "partial": snapshot.is_partial,
        "errors": [
            {
                "component": error.component,
                "error_message": error.error_message,
            }
            for error in snapshot.errors
        ],
        "system_health": (
            {
                "status": system_health.status.value,
                "checked_at": system_health.checked_at.isoformat(),
                "reasons": list(system_health.reasons),
                "requires_attention": system_health.requires_attention,
            }
            if system_health is not None
            else None
        ),
        "runtime_metrics": (
            {
                "generated_at": runtime_metrics.generated_at.isoformat(),
                "counts": {
                    metric.value: count
                    for metric, count in runtime_metrics.counts.items()
                },
                "error_rate": runtime_metrics.error_rate,
                "notification_failure_rate": (
                    runtime_metrics.notification_failure_rate
                ),
            }
            if runtime_metrics is not None
            else None
        ),
        "runtime_resource": (
            runtime_resource_evaluation_to_dict(runtime_resource)
            if runtime_resource is not None
            else None
        ),
        "runtime_health": (
            runtime_health_monitor_report_to_dict(runtime_health)
            if runtime_health is not None
            else None
        ),
        "portfolio": (
            {
                "generated_at": portfolio.generated_at.isoformat(),
                "currency": portfolio.currency,
                "cash_balance": portfolio.cash_balance,
                "buying_power": portfolio.buying_power,
                "broker_market_value": portfolio.broker_market_value,
                "broker_equity": portfolio.broker_equity,
                "position_count": portfolio.position_count,
                "total_market_value": portfolio.total_market_value,
                "total_unrealized_profit_loss": (
                    portfolio.total_unrealized_profit_loss
                ),
                "total_realized_profit_loss": (
                    portfolio.total_realized_profit_loss
                ),
                "positions": [
                    {
                        "position_id": position.position_id,
                        "code": position.code,
                        "side": position.side.value,
                        "quantity": position.quantity,
                        "average_cost": position.average_cost,
                        "market_price": position.market_price,
                        "market_value": position.market_value,
                        "unrealized_profit_loss": (
                            position.unrealized_profit_loss
                        ),
                        "realized_profit_loss": (
                            position.realized_profit_loss
                        ),
                    }
                    for position in portfolio.positions
                ],
            }
            if portfolio is not None
            else None
        ),
        "orders": (
            {
                "total_count": orders.total_count,
                "active_count": orders.active_count,
                "terminal_count": orders.terminal_count,
                "status_counts": {
                    status.value: count
                    for status, count in orders.status_counts.items()
                },
            }
            if orders is not None
            else None
        ),
        "live_summary": (
            {
                "trading_date": live_summary.trading_date.isoformat(),
                "log_count": live_summary.log_count,
                "cycle_started_count": live_summary.cycle_started_count,
                "cycle_completed_count": live_summary.cycle_completed_count,
                "market_poll_count": live_summary.market_poll_count,
                "signal_count": live_summary.signal_count,
                "risk_rejected_count": live_summary.risk_rejected_count,
                "risk_halted_count": live_summary.risk_halted_count,
                "order_count": live_summary.order_count,
                "execution_count": live_summary.execution_count,
                "error_count": live_summary.error_count,
                "critical_count": live_summary.critical_count,
                "codes": list(live_summary.codes),
            }
            if live_summary is not None
            else None
        ),
        "broker": (
            {
                "connected": broker.connected,
                "name": broker.name,
                "message": broker.message,
            }
            if broker is not None
            else None
        ),
    }
