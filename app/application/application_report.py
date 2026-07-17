"""Application LifecycleをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.application.application_models import (
    ApplicationReport,
    ApplicationSnapshot,
)


def application_snapshot_to_dict(
    snapshot: ApplicationSnapshot,
) -> dict[str, Any]:
    """Application Snapshotを辞書へ変換する。"""

    return {
        "application_name": snapshot.application_name,
        "state": snapshot.state.value,
        "created_at": snapshot.created_at.isoformat(),
        "checked_at": snapshot.checked_at.isoformat(),
        "started_at": (
            snapshot.started_at.isoformat()
            if snapshot.started_at is not None
            else None
        ),
        "stopping_at": (
            snapshot.stopping_at.isoformat()
            if snapshot.stopping_at is not None
            else None
        ),
        "stopped_at": (
            snapshot.stopped_at.isoformat()
            if snapshot.stopped_at is not None
            else None
        ),
        "stop_reason": (
            snapshot.stop_reason.value
            if snapshot.stop_reason is not None
            else None
        ),
        "message": snapshot.message,
        "uptime_seconds": snapshot.uptime_seconds,
        "is_running": snapshot.is_running,
        "is_terminal": snapshot.is_terminal,
    }


def application_report_to_dict(
    report: ApplicationReport,
) -> dict[str, Any]:
    """Application最終レポートを辞書へ変換する。"""

    return {
        "graceful_shutdown": report.graceful_shutdown,
        "snapshot": application_snapshot_to_dict(
            report.snapshot
        ),
    }
