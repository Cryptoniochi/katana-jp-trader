"""Watch List SQLite ORBバックテストのテスト。"""

import csv
from datetime import datetime
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.watchlist_sqlite import (
    WatchlistBacktestReportWriter,
    WatchlistSqliteOrbBacktestService,
)
from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def create_price(
    code: str,
    time_text: str,
    *,
    high: float,
    low: float,
    close: float,
) -> StockPrice:
    """テスト用5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"2026-07-13 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=200_000,
    )


def create_symbol_prices(
    code: str,
    final_close: float,
) -> list[StockPrice]:
    """ORB取引が1件発生する銘柄データを作成する。"""

    return [
        create_price(
            code,
            "09:00",
            high=1005,
            low=995,
            close=1000,
        ),
        create_price(
            code,
            "09:05",
            high=1008,
            low=998,
            close=1005,
        ),
        create_price(
            code,
            "09:10",
            high=1010,
            low=1000,
            close=1007,
        ),
        create_price(
            code,
            "09:15",
            high=1012,
            low=1005,
            close=1010,
        ),
        create_price(
            code,
            "09:20",
            high=1020,
            low=1008,
            close=1015,
        ),
        create_price(
            code,
            "14:50",
            high=max(1030, final_close),
            low=min(1005, final_close),
            close=final_close,
        ),
    ]


def create_service(
    tmp_path: Path,
) -> tuple[
    WatchlistSqliteOrbBacktestService,
    MarketBarRepository,
]:
    """テスト用サービスとRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    repository = MarketBarRepository(database_path)

    strategy = OpeningRangeBreakoutStrategy(
        quantity=100,
        stop_loss_rate=0.05,
        take_profit_rate=0.05,
        commission=0.0,
        slippage_rate=0.0,
    )

    service = WatchlistSqliteOrbBacktestService(
        repository=repository,
        strategy=strategy,
        engine=BacktestEngine(),
    )

    return service, repository


def run_report(
    service: WatchlistSqliteOrbBacktestService,
    codes: list[str],
):
    """固定期間でサービスを実行する。"""

    return service.run(
        codes=codes,
        interval_minutes=5,
        start_at=datetime(
            2026,
            7,
            13,
            0,
            0,
        ),
        end_at=datetime(
            2026,
            7,
            13,
            23,
            59,
            59,
        ),
    )


def test_service_backtests_all_watchlist_symbols(
    tmp_path: Path,
) -> None:
    """Watch List全銘柄を一括検証する。"""

    service, repository = create_service(tmp_path)

    repository.save_all(
        prices=[
            *create_symbol_prices(
                "7203",
                final_close=1025,
            ),
            *create_symbol_prices(
                "8306",
                final_close=1005,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = run_report(
        service,
        ["7203", "8306"],
    )

    assert report.symbol_count == 2
    assert report.data_symbol_count == 2
    assert report.traded_symbol_count == 2

    assert len(report.all_trades) == 2
    assert report.total_result.trade_count == 2


def test_service_includes_missing_symbol(
    tmp_path: Path,
) -> None:
    """SQLiteデータがない銘柄も結果へ含める。"""

    service, repository = create_service(tmp_path)

    repository.save_all(
        prices=create_symbol_prices(
            "7203",
            final_close=1025,
        ),
        interval_minutes=5,
        data_source="test",
    )

    report = run_report(
        service,
        ["7203", "9984"],
    )

    assert report.symbol_count == 2
    assert report.data_symbol_count == 1
    assert report.missing_codes == ["9984"]

    results_by_code = {item.code: item for item in report.symbol_results}

    assert results_by_code["9984"].source_bar_count == 0
    assert results_by_code["9984"].result.trade_count == 0


def test_service_ranks_profitable_symbol_first(
    tmp_path: Path,
) -> None:
    """利益の大きい銘柄を上位へ並べる。"""

    service, repository = create_service(tmp_path)

    repository.save_all(
        prices=[
            *create_symbol_prices(
                "7203",
                final_close=1030,
            ),
            *create_symbol_prices(
                "8306",
                final_close=1005,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = run_report(
        service,
        ["7203", "8306"],
    )

    assert report.symbol_results[0].code == "7203"
    assert report.symbol_results[1].code == "8306"


def test_service_removes_duplicate_codes(
    tmp_path: Path,
) -> None:
    """重複した銘柄コードを1件として扱う。"""

    service, repository = create_service(tmp_path)

    repository.save_all(
        prices=create_symbol_prices(
            "7203",
            final_close=1025,
        ),
        interval_minutes=5,
        data_source="test",
    )

    report = run_report(
        service,
        ["7203", "7203"],
    )

    assert report.symbol_count == 1


def test_report_writer_outputs_ranking(
    tmp_path: Path,
) -> None:
    """銘柄別ランキングをCSVへ出力できる。"""

    service, repository = create_service(tmp_path)

    repository.save_all(
        prices=[
            *create_symbol_prices(
                "7203",
                final_close=1030,
            ),
            *create_symbol_prices(
                "8306",
                final_close=1005,
            ),
        ],
        interval_minutes=5,
        data_source="test",
    )

    report = run_report(
        service,
        ["7203", "8306"],
    )

    file_path = tmp_path / "ranking.csv"

    output_path = WatchlistBacktestReportWriter().write_ranking(
        report=report,
        file_path=file_path,
    )

    assert output_path == file_path
    assert file_path.exists()

    with file_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert len(rows) == 2
    assert rows[0]["rank"] == "1"
    assert rows[0]["code"] == "7203"
    assert rows[1]["code"] == "8306"


@pytest.mark.parametrize(
    ("codes", "interval_minutes", "message"),
    [
        ([], 5, "銘柄コード"),
        (["ABCD"], 5, "数字"),
        (["7203"], 0, "時間足"),
    ],
)
def test_service_rejects_invalid_arguments(
    tmp_path: Path,
    codes: list[str],
    interval_minutes: int,
    message: str,
) -> None:
    """不正な銘柄コードまたは時間軸を拒否する。"""

    service, _repository = create_service(tmp_path)

    with pytest.raises(ValueError, match=message):
        service.run(
            codes=codes,
            interval_minutes=interval_minutes,
            start_at=datetime(
                2026,
                7,
                13,
            ),
            end_at=datetime(
                2026,
                7,
                13,
                23,
                59,
                59,
            ),
        )


def test_service_rejects_reversed_date_range(
    tmp_path: Path,
) -> None:
    """開始日時が終了日時より後なら拒否する。"""

    service, _repository = create_service(tmp_path)

    with pytest.raises(
        ValueError,
        match="開始日時",
    ):
        service.run(
            codes=["7203"],
            interval_minutes=5,
            start_at=datetime(
                2026,
                7,
                14,
            ),
            end_at=datetime(
                2026,
                7,
                13,
            ),
        )
