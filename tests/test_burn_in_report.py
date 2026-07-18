"""Burn-in JSONレポートのテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.burn_in_models import (
    BurnInResult,
    BurnInStopReason,
)
from app.runtime.burn_in_report import (
    burn_in_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_empty_result_is_json_compatible() -> None:
    result = BurnInResult(
        started_at=NOW,
        completed_at=NOW,
        stop_reason=BurnInStopReason.STOP_REQUESTED,
        samples=(),
    )

    payload = burn_in_result_to_dict(result)
    serialized = json.dumps(payload)

    assert payload["stop_reason"] == "stop_requested"
    assert payload["cycle_count"] == 0
    assert payload["samples"] == []
    assert "stop_requested" in serialized
