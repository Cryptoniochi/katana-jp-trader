"""イベント駆動BacktestRunnerとCLIのテスト。"""

import csv
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBarSeries,
)
from app.backtest.orb_signal_strategy import (
    OrbSignalStrategySettings,
)
from app.backtest.run_backtest import (
    _normalize_market_datetime,
    _parse_date,
    build_runner,
    load_series,
    main,
)
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice
from app.trading.order_models import OrderSide
from app.trading.trade_execution_repository import (
    TradeExecutionRepository,
)


JST = ZoneInfo("Asia/Tokyo")


def create_prices() -> list[StockPrice]:
    """BUYと利確EXITが発生する5分足を作成する。"""

    values = [
        (9, 0, 1000, 1000, 990, 995),
        (9, 5, 995, 1000, 990, 998),
        (9, 10, 998, 1000, 995, 999),
        (9, 15, 999, 1000, 995, 999),
        (9, 20, 1000, 1010, 999, 1005),
        (9, 25, 1005, 1020, 1000, 1015),
    ]

    return [
        StockPrice(
            code="7203",
            datetime=datetime(
                2026,
                7,
                1,
                hour,
                minute,
                tzinfo=JST,
            ),
            open=float(open_price),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=1000,
        )
        for (
            hour,
            minute,
            open_price,
            high,
            low,
            close,
        ) in values
    ]


def create_market_database(path: Path) -> None:
    initialize_database(path)
    MarketBarRepository(path).save_all(
        create_prices(),
        interval_minutes=5,
        data_source="test",
    )


def test_load_series_reads_five_minute_bars(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "market.db"
    create_market_database(database_path)

    series = load_series(
        database_path=database_path,
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    assert isinstance(series, HistoricalBarSeries)
    assert series.bar_count == 6
    assert series.code == "7203"


def test_event_runner_executes_buy_and_exit_at_signal_prices(
    tmp_path: Path,
) -> None:
    market_database = tmp_path / "market.db"
    state_database = tmp_path / "state.db"
    create_market_database(market_database)

    series = load_series(
        database_path=market_database,
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )
    runner = build_runner(
        series=series,
        state_database_path=state_database,
        initial_cash=1_000_000.0,
        strategy_settings=OrbSignalStrategySettings(
            quantity=100,
            take_profit_rate=0.01,
        ),
        commission=0.0,
        slippage_rate=0.0,
    )

    result = runner.run()

    assert result.signal_count == 2
    assert result.execution_count == 2
    assert result.portfolio_update_count == 2

    records = TradeExecutionRepository(
        state_database
    ).list_recent(limit=10)

    by_side = {
        record.execution.side: record.execution
        for record in records
    }

    assert by_side[OrderSide.BUY].execution_price == pytest.approx(
        1005.0
    )
    assert by_side[OrderSide.SELL].execution_price == pytest.approx(
        1015.05
    )


def test_cli_runs_and_prints_summary(
    tmp_path: Path,
    capsys,
) -> None:
    market_database = tmp_path / "market.db"
    state_database = tmp_path / "state.db"
    create_market_database(market_database)

    exit_code = main(
        [
            "--code",
            "7203",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-01",
            "--database",
            str(market_database),
            "--state-database",
            str(state_database),
            "--initial-cash",
            "1000000",
            "--take-profit-rate",
            "0.01",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Project KATANA ORB Backtest" in output
    assert "signals: 2" in output
    assert "executions: 2" in output
    assert "trades: 1" in output
    assert "win_rate: 100.00%" in output
    assert "profit_factor: N/A" in output
    assert state_database.exists()


def test_cli_writes_reports_to_requested_directory(
    tmp_path: Path,
) -> None:
    """--report-dirへ4種類のレポートを出力する。"""

    market_database = tmp_path / "market.db"
    state_database = tmp_path / "state.db"
    report_directory = tmp_path / "reports" / "run-001"
    create_market_database(market_database)

    exit_code = main(
        [
            "--code",
            "7203",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-01",
            "--database",
            str(market_database),
            "--state-database",
            str(state_database),
            "--report-dir",
            str(report_directory),
            "--initial-cash",
            "1000000",
            "--take-profit-rate",
            "0.01",
        ]
    )

    assert exit_code == 0
    assert (report_directory / "trades.csv").exists()
    assert (
        report_directory / "equity_curve.csv"
    ).exists()
    assert (report_directory / "metrics.csv").exists()
    assert (report_directory / "summary.json").exists()


def test_load_series_rejects_empty_period(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "market.db"
    initialize_database(database_path)

    with pytest.raises(ValueError, match="5分足"):
        load_series(
            database_path=database_path,
            code="7203",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )


def test_normalize_market_datetime_adds_jst() -> None:
    """タイムゾーンなし日時を日本時間として扱う。"""

    value = datetime(2026, 7, 1, 9, 0)

    normalized = _normalize_market_datetime(value)

    assert normalized.tzinfo == JST
    assert normalized.hour == 9


def test_normalize_market_datetime_converts_aware_value() -> None:
    """タイムゾーン付き日時も日本時間へ統一する。"""

    value = datetime(
        2026,
        7,
        1,
        0,
        0,
        tzinfo=ZoneInfo("UTC"),
    )

    normalized = _normalize_market_datetime(value)

    assert normalized.tzinfo == JST
    assert normalized.hour == 9


def test_parse_date_rejects_invalid_format() -> None:
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        _parse_date("2026/07/01")


def test_cli_runs_optimization_and_writes_reports(
    tmp_path: Path,
    capsys,
) -> None:
    """--optimizeで全組み合わせとランキングを出力する。"""

    market_database = tmp_path / "market.db"
    report_directory = tmp_path / "optimization"
    create_market_database(market_database)

    exit_code = main(
        [
            "--code",
            "7203",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-01",
            "--database",
            str(market_database),
            "--report-dir",
            str(report_directory),
            "--initial-cash",
            "1000000",
            "--optimize",
            "--stop-loss-candidates",
            "0.01,0.02",
            "--take-profit-candidates",
            "0.01",
            "--opening-range-end-candidates",
            "09:15",
            "--optimization-top-n",
            "2",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Project KATANA ORB Optimization" in output
    assert "combinations: 2" in output
    assert "ranking_method: net_profit" in output
    assert (report_directory / "optimization.csv").exists()
    assert (report_directory / "optimization.json").exists()


def test_cli_runs_composite_optimization(
    tmp_path: Path,
    capsys,
) -> None:
    """--ranking compositeで複合ランキングを出力する。"""

    market_database = tmp_path / "market.db"
    report_directory = tmp_path / "composite"
    create_market_database(market_database)

    exit_code = main(
        [
            "--code",
            "7203",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-01",
            "--database",
            str(market_database),
            "--report-dir",
            str(report_directory),
            "--initial-cash",
            "1000000",
            "--optimize",
            "--stop-loss-candidates",
            "0.01,0.02",
            "--take-profit-candidates",
            "0.01",
            "--opening-range-end-candidates",
            "09:15",
            "--ranking",
            "composite",
            "--top-n",
            "1",
            "--weight-net-profit",
            "4",
            "--weight-profit-factor",
            "3",
            "--weight-win-rate",
            "2",
            "--weight-drawdown",
            "1",
        ]
    )

    output = capsys.readouterr().out
    csv_path = report_directory / "optimization.csv"
    json_path = report_directory / "optimization.json"

    with csv_path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    payload = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert "ranking_method: composite" in output
    assert "composite_score=" in output
    assert csv_path.exists()
    assert json_path.exists()
    assert "composite_score" in rows[0]
    assert "net_profit_score" in rows[0]
    assert "profit_factor_score" in rows[0]
    assert "win_rate_score" in rows[0]
    assert "drawdown_score" in rows[0]
    assert payload["ranking_method"] == "composite"
    assert payload["best_parameter"] is not None
    assert payload["best_score"] is not None
    assert payload["weights"] == {
        "maximum_drawdown": 0.1,
        "net_profit": 0.4,
        "profit_factor": 0.3,
        "win_rate": 0.2,
    }
    assert len(payload["ranking"]) == 1
