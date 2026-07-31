"""HighBreakoutReporterのテスト。"""

from datetime import date

import json

from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
    HighBreakoutType,
)
from app.strategy.high_breakout_reporter import (
    HighBreakoutReporter,
)


def candidate() -> HighBreakoutCandidate:
    return HighBreakoutCandidate(
        code="7203",
        trading_date=date(2026, 8, 3),
        breakout_types=(
            HighBreakoutType.DAY_20,
            HighBreakoutType.DAY_60,
        ),
        close_price=3000.0,
        previous_20_day_high=2950.0,
        previous_60_day_high=2980.0,
        previous_year_high=2990.0,
        volume_ratio=2.5,
        turnover=750_000_000.0,
        atr=60.0,
        atr_rate=0.02,
        score=88.0,
    )


def test_reporter_writes_all_outputs(
    tmp_path,
) -> None:
    paths = HighBreakoutReporter(
        tmp_path
    ).write((candidate(),))

    assert all(
        path.exists()
        for path in paths
    )

    json_path, csv_path, html_path, summary_path = paths

    payload = json.loads(
        json_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload[0]["code"] == "7203"
    assert "7203" in csv_path.read_text(
        encoding="utf-8-sig"
    )
    assert "Project KATANA" in html_path.read_text(
        encoding="utf-8"
    )
    assert "candidate_count=1" in summary_path.read_text(
        encoding="utf-8"
    )
