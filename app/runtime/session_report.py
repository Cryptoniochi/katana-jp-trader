"""長時間運転セッションレポートをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.session_models import (
    RuntimeSessionReport,
    RuntimeSessionSnapshot,
)


def runtime_session_snapshot_to_dict(
    snapshot: RuntimeSessionSnapshot,
) -> dict[str, Any]:
    return {
        "session_id": snapshot.session_id,
        "status": snapshot.status.value,
        "started_at": snapshot.started_at.isoformat(),
        "checked_at": snapshot.checked_at.isoformat(),
        "active_date": snapshot.active_date.isoformat(),
        "cycle_count": snapshot.cycle_count,
        "successful_cycle_count": snapshot.successful_cycle_count,
        "failed_cycle_count": snapshot.failed_cycle_count,
        "heartbeat_count": snapshot.heartbeat_count,
        "restart_count": snapshot.restart_count,
        "error_count": snapshot.error_count,
        "completed_day_count": snapshot.completed_day_count,
        "last_heartbeat_at": (
            snapshot.last_heartbeat_at.isoformat()
            if snapshot.last_heartbeat_at is not None
            else None
        ),
        "last_cycle_at": (
            snapshot.last_cycle_at.isoformat()
            if snapshot.last_cycle_at is not None
            else None
        ),
        "uptime_seconds": snapshot.uptime_seconds,
        "ended_at": (
            snapshot.ended_at.isoformat()
            if snapshot.ended_at is not None
            else None
        ),
        "stop_reason": (
            snapshot.stop_reason.value
            if snapshot.stop_reason is not None
            else None
        ),
        "message": snapshot.message,
    }


def runtime_session_report_to_dict(
    report: RuntimeSessionReport,
) -> dict[str, Any]:
    return {
        "session": runtime_session_snapshot_to_dict(report.snapshot),
        "total_cycle_count": report.total_cycle_count,
        "total_error_count": report.total_error_count,
        "daily_summaries": [
            {
                "session_id": item.session_id,
                "operating_date": item.operating_date.isoformat(),
                "started_at": item.started_at.isoformat(),
                "ended_at": item.ended_at.isoformat(),
                "duration_seconds": item.duration_seconds,
                "cycle_count": item.cycle_count,
                "successful_cycle_count": item.successful_cycle_count,
                "failed_cycle_count": item.failed_cycle_count,
                "success_rate": item.success_rate,
                "heartbeat_count": item.heartbeat_count,
                "restart_count": item.restart_count,
                "error_count": item.error_count,
            }
            for item in report.daily_summaries
        ],
    }
