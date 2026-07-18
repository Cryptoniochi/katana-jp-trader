"""Dashboard Snapshot Publish結果をJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.dashboard.dashboard_snapshot_publish_service import (
    DashboardSnapshotPublishResult,
)


def dashboard_snapshot_publish_result_to_dict(
    result: DashboardSnapshotPublishResult,
) -> dict[str, Any]:
    """Publish結果を辞書へ変換する。"""

    return {
        "generated_at": (
            result.write_result.generated_at.isoformat()
        ),
        "output_path": str(
            result.write_result.output_path
        ),
        "size_bytes": result.write_result.size_bytes,
        "complete": result.snapshot.is_complete,
        "partial": result.snapshot.is_partial,
        "unavailable_components": list(
            result.snapshot.unavailable_components
        ),
    }
