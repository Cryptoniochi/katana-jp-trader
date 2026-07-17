"""Runtime Resource履歴統計をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.resource_monitor import (
    RuntimeResourceHistorySummary,
)
from app.runtime.resource_report import (
    runtime_resource_evaluation_to_dict,
)


def runtime_resource_history_summary_to_dict(
    summary: RuntimeResourceHistorySummary,
) -> dict[str, Any]:
    """履歴統計を辞書へ変換する。"""

    return {
        "sample_count": summary.sample_count,
        "average_cpu_percent": (
            summary.average_cpu_percent
        ),
        "maximum_cpu_percent": (
            summary.maximum_cpu_percent
        ),
        "average_rss_bytes": (
            summary.average_rss_bytes
        ),
        "maximum_rss_bytes": (
            summary.maximum_rss_bytes
        ),
        "maximum_vms_bytes": (
            summary.maximum_vms_bytes
        ),
        "maximum_thread_count": (
            summary.maximum_thread_count
        ),
        "latest": (
            runtime_resource_evaluation_to_dict(
                summary.latest
            )
            if summary.latest is not None
            else None
        ),
    }
