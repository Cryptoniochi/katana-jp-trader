"""Paper Trading Day JSON変換のテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_day_report import (
    paper_trading_day_result_to_dict,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_day_result_is_json_compatible() -> None:
    summary = PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
    )
    record = PaperTradingDailyRecord(
        trading_date=NOW.date(),
        status=PaperTradingRuntimeStatus.COMPLETED,
        started_at=NOW,
        completed_at=NOW,
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        signal_count=0,
        execution_count=0,
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
        net_profit_loss=10_000.0,
        return_rate=0.01,
        error_message=None,
        payload={},
        created_at=NOW,
        updated_at=NOW,
    )
    result = PaperTradingDayResult(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        stop_reason=PaperTradingDayStopReason.MARKET_CLOSED,
        summary=summary,
        record=record,
    )

    payload = paper_trading_day_result_to_dict(result)
    serialized = json.dumps(payload)

    assert payload["stop_reason"] == "market_closed"
    assert payload["net_profit_loss"] == 10_000.0
    assert payload["summary"]["status"] == "completed"
    assert "market_closed" in serialized
