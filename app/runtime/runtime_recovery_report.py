"""RuntimeRecoveryResultをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.recovery_report import (
    recovery_result_to_dict,
)
from app.runtime.runtime_health_monitor_report import (
    runtime_health_monitor_report_to_dict,
)
from app.runtime.runtime_recovery_models import (
    RuntimeRecoveryResult,
)


def runtime_recovery_result_to_dict(
    result: RuntimeRecoveryResult,
) -> dict[str, Any]:
    """Runtime復旧結果を辞書へ変換する。"""

    return {
        "runtime_name": result.runtime_name,
        "recovery_attempted": (
            result.recovery_attempted
        ),
        "recovered": result.recovered,
        "requires_attention": (
            result.requires_attention
        ),
        "initial_health": (
            runtime_health_monitor_report_to_dict(
                result.initial_health
            )
        ),
        "recovery": (
            recovery_result_to_dict(
                result.recovery_result
            )
            if result.recovery_result is not None
            else None
        ),
        "final_health": (
            runtime_health_monitor_report_to_dict(
                result.final_health
            )
        ),
    }
