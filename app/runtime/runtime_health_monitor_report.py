"""Runtime Health Monitor結果をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
)


def runtime_health_monitor_report_to_dict(
    report: RuntimeHealthMonitorReport,
) -> dict[str, Any]:
    """Runtime Health Monitor結果を辞書へ変換する。"""

    return {
        "status": report.status.value,
        "checked_at": report.checked_at.isoformat(),
        "running": report.running,
        "heartbeat_age_seconds": (
            report.heartbeat_age_seconds
        ),
        "cycle_age_seconds": (
            report.cycle_age_seconds
        ),
        "requires_attention": (
            report.requires_attention
        ),
        "reasons": list(report.reasons),
    }
