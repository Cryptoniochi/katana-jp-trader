"""BrokerRecoveryResultをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.broker_recovery_models import (
    BrokerRecoveryResult,
)
from app.runtime.recovery_report import (
    recovery_result_to_dict,
)


def broker_recovery_result_to_dict(
    result: BrokerRecoveryResult,
) -> dict[str, Any]:
    """Broker復旧結果を辞書へ変換する。"""

    def health_to_dict(health) -> dict[str, Any]:
        return {
            "broker_name": health.broker_name,
            "status": health.status.value,
            "checked_at": health.checked_at.isoformat(),
            "account_accessible": (
                health.account_accessible
            ),
            "orders_accessible": (
                health.orders_accessible
            ),
            "positions_accessible": (
                health.positions_accessible
            ),
            "active_order_count": (
                health.active_order_count
            ),
            "position_count": health.position_count,
            "error_messages": list(
                health.error_messages
            ),
        }

    return {
        "broker_name": result.broker_name,
        "recovery_attempted": (
            result.recovery_attempted
        ),
        "recovered": result.recovered,
        "initial_health": health_to_dict(
            result.initial_health
        ),
        "recovery": (
            recovery_result_to_dict(
                result.recovery_result
            )
            if result.recovery_result is not None
            else None
        ),
        "final_health": health_to_dict(
            result.final_health
        ),
    }
