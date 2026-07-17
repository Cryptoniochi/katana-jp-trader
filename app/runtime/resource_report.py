"""Runtime ResourceモデルをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.resource_models import (
    RuntimeResourceEvaluation,
    RuntimeResourceSnapshot,
    RuntimeResourceThresholds,
)


def runtime_resource_snapshot_to_dict(
    snapshot: RuntimeResourceSnapshot,
) -> dict[str, Any]:
    """1回分のリソース計測値を辞書へ変換する。"""

    return {
        "sampled_at": snapshot.sampled_at.isoformat(),
        "cpu_percent": snapshot.cpu_percent,
        "rss_bytes": snapshot.rss_bytes,
        "rss_megabytes": snapshot.rss_megabytes,
        "vms_bytes": snapshot.vms_bytes,
        "vms_megabytes": snapshot.vms_megabytes,
        "thread_count": snapshot.thread_count,
        "process_uptime_seconds": (
            snapshot.process_uptime_seconds
        ),
    }


def runtime_resource_evaluation_to_dict(
    evaluation: RuntimeResourceEvaluation,
) -> dict[str, Any]:
    """閾値判定結果を辞書へ変換する。"""

    return {
        "status": evaluation.status.value,
        "requires_attention": evaluation.requires_attention,
        "reasons": list(evaluation.reasons),
        "snapshot": runtime_resource_snapshot_to_dict(
            evaluation.snapshot
        ),
    }


def runtime_resource_thresholds_to_dict(
    thresholds: RuntimeResourceThresholds,
) -> dict[str, Any]:
    """リソース閾値設定を辞書へ変換する。"""

    return {
        "cpu_warning_percent": (
            thresholds.cpu_warning_percent
        ),
        "cpu_critical_percent": (
            thresholds.cpu_critical_percent
        ),
        "rss_warning_bytes": (
            thresholds.rss_warning_bytes
        ),
        "rss_critical_bytes": (
            thresholds.rss_critical_bytes
        ),
        "thread_warning_count": (
            thresholds.thread_warning_count
        ),
        "thread_critical_count": (
            thresholds.thread_critical_count
        ),
    }
