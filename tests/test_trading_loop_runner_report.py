"""Trading Loop Runner JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
    TradingLoopRunnerStopReason,
)
from app.application.trading_loop_runner_report import (
    trading_loop_runner_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_empty_runner_result_is_json_compatible() -> None:
    result = TradingLoopRunnerResult(
        started_at=NOW,
        completed_at=NOW,
        stop_reason=(
            TradingLoopRunnerStopReason.STOP_REQUESTED
        ),
        cycles=(),
    )

    payload = trading_loop_runner_result_to_dict(
        result
    )
    serialized = json.dumps(payload)

    assert payload["stop_reason"] == "stop_requested"
    assert payload["cycle_count"] == 0
    assert payload["cycles"] == []
    assert "stop_requested" in serialized
