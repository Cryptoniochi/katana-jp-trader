"""複数CSV履歴読込機能のテスト。"""

import csv
from pathlib import Path

import pytest

from app.market.historical_csv_reader import HistoricalCsvReader


def write_prices_csv(
    file_path: Path,
    rows: list[list[object]],
) -> None:
    """テスト用株価CSVを作成する。"""

    with file_path.open(
        mode="w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "code",
                "traded_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

        writer.writerows(rows)


def test_reader_loads_multiple_csv_files_in_time_order(
    tmp_path: Path,
) -> None:
    """複数CSVを読み込み、日時順に並べられる。"""

    write_prices_csv(
        tmp_path / "day2.csv",
        [
            [
                "7203",
                "2026-07-14T09:00:00",
                3530,
                3540,
                3520,
                3535,
                120000,
            ]
        ],
    )

    write_prices_csv(
        tmp_path / "day1.csv",
        [
            [
                "7203",
                "2026-07-13T09:00:00",
                3500,
                3520,
                3490,
                3510,
                100000,
            ]
        ],
    )

    prices = HistoricalCsvReader().read_directory(tmp_path)

    assert len(prices) == 2
    assert prices[0].datetime.isoformat() == "2026-07-13T09:00:00"
    assert prices[1].datetime.isoformat() == "2026-07-14T09:00:00"


def test_reader_filters_by_stock_code(
    tmp_path: Path,
) -> None:
    """指定銘柄だけを抽出できる。"""

    write_prices_csv(
        tmp_path / "prices.csv",
        [
            [
                "7203",
                "2026-07-13T09:00:00",
                3500,
                3520,
                3490,
                3510,
                100000,
            ],
            [
                "9984",
                "2026-07-13T09:00:00",
                11000,
                11100,
                10900,
                11050,
                200000,
            ],
        ],
    )

    prices = HistoricalCsvReader().read_directory(
        tmp_path,
        code="7203",
    )

    assert len(prices) == 1
    assert prices[0].code == "7203"


def test_reader_removes_duplicate_bars(
    tmp_path: Path,
) -> None:
    """同じ銘柄・同じ日時の足を重複させない。"""

    duplicate_row = [
        "7203",
        "2026-07-13T09:00:00",
        3500,
        3520,
        3490,
        3510,
        100000,
    ]

    write_prices_csv(
        tmp_path / "first.csv",
        [duplicate_row],
    )
    write_prices_csv(
        tmp_path / "second.csv",
        [duplicate_row],
    )

    prices = HistoricalCsvReader().read_directory(tmp_path)

    assert len(prices) == 1


def test_reader_rejects_empty_directory(
    tmp_path: Path,
) -> None:
    """CSVがないフォルダを拒否する。"""

    with pytest.raises(
        FileNotFoundError,
        match="CSVファイルがありません",
    ):
        HistoricalCsvReader().read_directory(tmp_path)


def test_reader_rejects_invalid_ohlc(
    tmp_path: Path,
) -> None:
    """高値・安値の関係が不正な足を拒否する。"""

    write_prices_csv(
        tmp_path / "invalid.csv",
        [
            [
                "7203",
                "2026-07-13T09:00:00",
                3500,
                3490,
                3480,
                3510,
                100000,
            ]
        ],
    )

    with pytest.raises(ValueError, match="高値"):
        HistoricalCsvReader().read_directory(tmp_path)
