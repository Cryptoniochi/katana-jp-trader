"""Runtime Session JSON変換のテスト。"""

import json
from datetime import datetime, timedelta, timezone

from app.runtime.session_models import RuntimeSessionStopReason
from app.runtime.session_report import runtime_session_report_to_dict
from app.runtime.session_service import RuntimeSessionService


def test_report_is_json_compatible() -> None:
    current = datetime(2026, 7, 18, tzinfo=timezone.utc)

    def now_provider() -> datetime:
        return current

    service = RuntimeSessionService(
        now_provider=now_provider,
        session_id_provider=lambda: "session-1",
    )
    service.start()
    service.record_cycle(successful=True)
    report = service.stop(
        reason=RuntimeSessionStopReason.NORMAL
    )

    payload = runtime_session_report_to_dict(report)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["session"]["status"] == "stopped"
    assert payload["total_cycle_count"] == 1
    assert payload["daily_summaries"][0]["success_rate"] == 1.0
    assert "session-1" in serialized
