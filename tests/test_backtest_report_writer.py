"""バックテストCSVレポートのテスト。"""

import csv
from datetime import datetime
from pathlib import Path

import pytest

from app.backtest.report_writer import BacktestReportWriter
from app.backtest.trade import Trade


def test_writer_outputs_trade_details(
    tmp_path: Path,
) -> None:
    """取引明細をCSVへ正しく出力できる。"""

    trade = Trade(
        code="7203",
        buy_price=3500.0,
        sell_price=3515.0,
        quantity=100,
        commission=100.0,
        slippage_rate=0.0005,
        entry_at=datetime(2026, 7, 13, 9, 25),
        exit_at=datetime(2026, 7, 13, 15, 30),
    )

    file_path = tmp_path / "report.csv"

    result_path = BacktestReportWriter().write_trades(
        [trade],
        file_path,
    )

    assert result_path == file_path
    assert file_path.exists()

    with file_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 1
    assert rows[0]["code"] == "7203"
    assert rows[0]["entry_at"] == "2026-07-13T09:25:00"
    assert rows[0]["exit_at"] == "2026-07-13T15:30:00"
    assert float(rows[0]["net_profit"]) == pytest.approx(trade.profit)
