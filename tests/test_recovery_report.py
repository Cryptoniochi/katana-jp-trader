"""RecoveryResult JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)
from app.runtime.recovery_report import (
    recovery_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_recovery_result_is_json_compatible() -> None:
    attempt = RecoveryAttempt(
        attempt_number=1,
        started_at=NOW,
        completed_at=NOW,
        successful=True,
        error_message=None,
        delay_seconds_before_attempt=0.0,
    )
    result = RecoveryResult(
        recovery_name="broker reconnect",
        status=RecoveryStatus.SUCCESS,
        started_at=NOW,
        completed_at=NOW,
        attempts=(attempt,),
    )

    payload = recovery_result_to_dict(result)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert payload["status"] == "success"
    assert payload["attempt_count"] == 1
    assert payload["succeeded"] is True
    assert "broker reconnect" in serialized
