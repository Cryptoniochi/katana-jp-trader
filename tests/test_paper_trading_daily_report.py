"""Paper Trading日次レポートのテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.paper_trading_daily_report import (
    paper_trading_daily_summary_to_dict,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_empty_daily_summary_is_json_compatible() -> None:
    summary = PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_000_000.0,
    )

    payload = paper_trading_daily_summary_to_dict(
        summary
    )
    serialized = json.dumps(payload)

    assert payload["status"] == "completed"
    assert payload["cycle_count"] == 0
    assert payload["net_profit_loss"] == 0.0
    assert payload["return_rate"] == 0.0
    assert "completed" in serialized
