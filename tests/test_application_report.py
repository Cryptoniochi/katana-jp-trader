"""Application Lifecycle JSON変換のテスト。"""

import json
from datetime import datetime, timedelta, timezone

from app.application.application_models import (
    ApplicationStopReason,
)
from app.application.application_report import (
    application_report_to_dict,
    application_snapshot_to_dict,
)
from app.application.application_runner import (
    ApplicationRunner,
)


BASE = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_running_snapshot_is_json_compatible() -> None:
    current = BASE

    def now_provider() -> datetime:
        return current

    runner = ApplicationRunner(
        now_provider=now_provider
    )
    runner.start()

    payload = application_snapshot_to_dict(
        runner.snapshot()
    )
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert payload["state"] == "running"
    assert payload["is_running"] is True
    assert payload["is_terminal"] is False
    assert "Project KATANA" in serialized


def test_final_report_contains_shutdown_information() -> None:
    current = BASE

    def now_provider() -> datetime:
        return current

    runner = ApplicationRunner(
        now_provider=now_provider
    )
    runner.start()
    current += timedelta(seconds=30)

    report = runner.stop(
        reason=ApplicationStopReason.MANUAL,
        message="operator requested",
    )
    payload = application_report_to_dict(report)

    assert payload["graceful_shutdown"] is True
    assert payload["snapshot"]["state"] == "stopped"
    assert payload["snapshot"]["stop_reason"] == "manual"
    assert payload["snapshot"]["message"] == (
        "operator requested"
    )
    assert payload["snapshot"]["uptime_seconds"] == 30.0
