"""DailyReportServiceのテスト。"""

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from app.runtime.daily_report_models import (
    DailyReportStatus,
)
from app.runtime.daily_report_service import (
    DailyReportService,
    DailyTradeRecord,
    SQLiteDailyTradeRepository,
)


REPORT_DATE = date(2026, 8, 3)
NOW = datetime(
    2026,
    8,
    3,
    15,
    40,
    tzinfo=timezone.utc,
)


class FakeRepository:
    def __init__(
        self,
        records,
    ) -> None:
        self.records = tuple(records)

    def list_closed_trades(
        self,
        report_date,
    ):
        assert report_date == REPORT_DATE
        return self.records


def record(
    *,
    symbol: str,
    strategy: str,
    pnl: float,
    minute: int,
) -> DailyTradeRecord:
    return DailyTradeRecord(
        closed_at=datetime(
            2026,
            8,
            3,
            6,
            minute,
            tzinfo=timezone.utc,
        ),
        symbol=symbol,
        strategy_name=strategy,
        realized_profit_loss=pnl,
    )


def test_service_calculates_daily_metrics() -> None:
    service = DailyReportService(
        FakeRepository(
            (
                record(
                    symbol="7203",
                    strategy="orb",
                    pnl=1000.0,
                    minute=1,
                ),
                record(
                    symbol="6758",
                    strategy="orb",
                    pnl=-400.0,
                    minute=2,
                ),
                record(
                    symbol="7203",
                    strategy="pullback",
                    pnl=500.0,
                    minute=3,
                ),
                record(
                    symbol="9984",
                    strategy="pullback",
                    pnl=0.0,
                    minute=4,
                ),
            )
        )
    )

    report = service.generate(
        report_date=REPORT_DATE,
        generated_at=NOW,
    )

    assert report.status is DailyReportStatus.COMPLETE
    assert report.summary.trade_count == 4
    assert report.summary.win_count == 2
    assert report.summary.loss_count == 1
    assert report.summary.flat_count == 1
    assert report.summary.net_profit_loss == 1100.0
    assert report.summary.gross_profit == 1500.0
    assert report.summary.gross_loss == -400.0
    assert report.summary.profit_factor == 3.75
    assert report.summary.maximum_drawdown == -400.0

    # Breakdown rows are sorted by net P/L descending.
    assert report.strategy_breakdown[0].key == "orb"
    assert (
        report.strategy_breakdown[0].net_profit_loss
        == 600.0
    )
    assert report.strategy_breakdown[1].key == "pullback"
    assert (
        report.strategy_breakdown[1].net_profit_loss
        == 500.0
    )

    assert report.symbol_breakdown[0].key == "7203"
    assert (
        report.symbol_breakdown[0].net_profit_loss
        == 1500.0
    )


def test_empty_report_is_generated() -> None:
    report = DailyReportService(
        FakeRepository(())
    ).generate(
        report_date=REPORT_DATE,
        generated_at=NOW,
    )

    assert report.status is DailyReportStatus.EMPTY
    assert report.summary.trade_count == 0
    assert report.summary.win_rate is None


def test_notes_make_non_empty_report_partial() -> None:
    report = DailyReportService(
        FakeRepository(
            (
                record(
                    symbol="7203",
                    strategy="orb",
                    pnl=1000.0,
                    minute=1,
                ),
            )
        )
    ).generate(
        report_date=REPORT_DATE,
        generated_at=NOW,
        notes=("Recovery log unavailable.",),
    )

    assert report.status is DailyReportStatus.PARTIAL


def test_generate_and_save_writes_json(
    tmp_path: Path,
) -> None:
    output = tmp_path / "daily.json"
    report = DailyReportService(
        FakeRepository(())
    ).generate_and_save(
        report_date=REPORT_DATE,
        generated_at=NOW,
        output_path=output,
    )

    payload = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert payload["status"] == "empty"
    assert payload["report_date"] == "2026-08-03"
    assert (
        payload["summary"]["trade_count"]
        == report.summary.trade_count
    )


def test_sqlite_repository_detects_supported_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE trade_journal (
                closed_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                realized_profit_loss REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trade_journal (
                closed_at,
                symbol,
                strategy_name,
                realized_profit_loss
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "2026-08-03T06:00:00+00:00",
                "7203",
                "orb",
                1000.0,
            ),
        )
        connection.commit()

    records = SQLiteDailyTradeRepository(
        database
    ).list_closed_trades(
        REPORT_DATE
    )

    assert len(records) == 1
    assert records[0].symbol == "7203"
    assert records[0].realized_profit_loss == 1000.0
