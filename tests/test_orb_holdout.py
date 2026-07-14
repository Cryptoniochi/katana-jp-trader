"""ORBホールドアウト検証のテスト。"""

import csv
from pathlib import Path

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.orb_holdout import OrbHoldoutValidator
from app.backtest.orb_optimizer import OrbOptimizer
from app.market.historical_csv_reader import HistoricalCsvReader


def write_day_rows(
    writer: csv.writer,
    day: int,
    final_close: float,
) -> None:
    """指定日のORB用5分足を書き込む。"""

    date_text = f"2026-07-{day:02d}"

    rows = [
        [
            "7203",
            f"{date_text}T09:00:00",
            1000,
            1005,
            995,
            1000,
            100000,
        ],
        [
            "7203",
            f"{date_text}T09:15:00",
            1000,
            1010,
            998,
            1005,
            120000,
        ],
        [
            "7203",
            f"{date_text}T09:20:00",
            1005,
            1020,
            1004,
            1010,
            180000,
        ],
        [
            "7203",
            f"{date_text}T14:50:00",
            1010,
            max(1020, final_close),
            min(1000, final_close),
            final_close,
            300000,
        ],
    ]

    writer.writerows(rows)


def write_holdout_csv(file_path: Path) -> None:
    """4営業日分のテスト用CSVを作成する。"""

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

        write_day_rows(writer, 13, 1030)
        write_day_rows(writer, 14, 1025)
        write_day_rows(writer, 15, 995)
        write_day_rows(writer, 16, 1040)


def create_validator(
    training_ratio: float = 0.5,
) -> OrbHoldoutValidator:
    """テスト用バリデーターを作成する。"""

    reader = HistoricalCsvReader()
    engine = BacktestEngine()

    optimizer = OrbOptimizer(
        historical_reader=reader,
        engine=engine,
        quantity=100,
        commission=0.0,
        slippage_rate=0.0,
    )

    return OrbHoldoutValidator(
        historical_reader=reader,
        optimizer=optimizer,
        engine=engine,
        training_ratio=training_ratio,
    )


def test_holdout_splits_dates_chronologically(
    tmp_path: Path,
) -> None:
    """古い日付を学習、新しい日付を検証に使う。"""

    write_holdout_csv(tmp_path / "prices.csv")

    result = create_validator().run(
        directory=tmp_path,
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    assert result.training_day_count == 2
    assert result.validation_day_count == 2

    assert result.training_start.isoformat() == "2026-07-13"
    assert result.training_end.isoformat() == "2026-07-14"
    assert result.validation_start.isoformat() == "2026-07-15"
    assert result.validation_end.isoformat() == "2026-07-16"


def test_holdout_uses_best_training_parameters_for_validation(
    tmp_path: Path,
) -> None:
    """学習期間の最良条件を検証期間へ適用する。"""

    write_holdout_csv(tmp_path / "prices.csv")

    result = create_validator().run(
        directory=tmp_path,
        stop_loss_rates=[0.01, 0.02],
        take_profit_rates=[0.01, 0.02],
    )

    assert result.best_parameters.trade_count == 2
    assert result.validation_result.trade_count == 2


def test_holdout_writes_csv_report(
    tmp_path: Path,
) -> None:
    """ホールドアウト結果をCSVへ出力できる。"""

    write_holdout_csv(tmp_path / "prices.csv")

    validator = create_validator()

    result = validator.run(
        directory=tmp_path,
        stop_loss_rates=[0.01],
        take_profit_rates=[0.02],
    )

    report_path = tmp_path / "holdout.csv"

    output_path = validator.write_csv(
        result=result,
        file_path=report_path,
    )

    assert output_path == report_path
    assert report_path.exists()


def test_holdout_rejects_single_trading_day(
    tmp_path: Path,
) -> None:
    """1営業日だけでは分割できない。"""

    csv_path = tmp_path / "prices.csv"

    with csv_path.open(
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

        write_day_rows(writer, 13, 1030)

    with pytest.raises(ValueError, match="2営業日以上"):
        create_validator().run(
            directory=tmp_path,
            stop_loss_rates=[0.01],
            take_profit_rates=[0.02],
        )


@pytest.mark.parametrize(
    "training_ratio",
    [0.0, 1.0, -0.1, 1.1],
)
def test_holdout_rejects_invalid_training_ratio(
    training_ratio: float,
) -> None:
    """0以下または1以上の学習割合を拒否する。"""

    with pytest.raises(ValueError, match="学習期間"):
        create_validator(training_ratio=training_ratio)
