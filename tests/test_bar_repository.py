"""市場時間足Repositoryのテスト。"""

from datetime import datetime
from pathlib import Path

import pytest

from app.database import initialize_database
from app.market.bar_repository import (
    MarketBarRepository,
)
from app.market.models import StockPrice


def create_price(
    time_text: str,
    *,
    code: str = "7203",
    close: float = 1005.0,
    volume: int = 1000,
) -> StockPrice:
    """テスト用5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"2026-07-13 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=1000.0,
        high=max(1010.0, close),
        low=min(995.0, close),
        close=close,
        volume=volume,
    )


def create_repository(
    tmp_path: Path,
) -> MarketBarRepository:
    """初期化済みのテスト用Repositoryを返す。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return MarketBarRepository(database_path)


def test_repository_saves_and_reads_bars(
    tmp_path: Path,
) -> None:
    """複数の5分足を保存して読み込める。"""

    repository = create_repository(tmp_path)

    prices = [
        create_price("09:00"),
        create_price(
            "09:05",
            close=1010.0,
            volume=2000,
        ),
    ]

    saved_count = repository.save_all(
        prices=prices,
        interval_minutes=5,
        data_source="jquants",
    )

    loaded_prices = repository.read(
        code="7203",
        interval_minutes=5,
    )

    assert saved_count == 2
    assert len(loaded_prices) == 2

    assert loaded_prices[0].datetime == datetime(
        2026,
        7,
        13,
        9,
        0,
    )
    assert loaded_prices[1].close == pytest.approx(1010.0)
    assert loaded_prices[1].volume == 2000


def test_repository_upserts_duplicate_bar(
    tmp_path: Path,
) -> None:
    """同じ足を再保存しても件数を増やさず更新する。"""

    repository = create_repository(tmp_path)

    repository.save_all(
        prices=[
            create_price(
                "09:00",
                close=1005.0,
                volume=1000,
            )
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    repository.save_all(
        prices=[
            create_price(
                "09:00",
                close=1008.0,
                volume=1500,
            )
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    loaded_prices = repository.read(
        code="7203",
        interval_minutes=5,
    )

    assert (
        repository.count(
            code="7203",
            interval_minutes=5,
        )
        == 1
    )

    assert loaded_prices[0].close == pytest.approx(1008.0)
    assert loaded_prices[0].volume == 1500


def test_repository_separates_intervals(
    tmp_path: Path,
) -> None:
    """同じ日時でも異なる時間軸は別データとして保存する。"""

    repository = create_repository(tmp_path)
    price = create_price("09:00")

    repository.save_all(
        prices=[price],
        interval_minutes=1,
        data_source="jquants",
    )
    repository.save_all(
        prices=[price],
        interval_minutes=5,
        data_source="jquants",
    )

    assert (
        repository.count(
            code="7203",
        )
        == 2
    )

    assert (
        repository.count(
            code="7203",
            interval_minutes=5,
        )
        == 1
    )


def test_repository_reads_date_range(
    tmp_path: Path,
) -> None:
    """開始日時・終了日時の範囲で読み込める。"""

    repository = create_repository(tmp_path)

    repository.save_all(
        prices=[
            create_price("09:00"),
            create_price("09:05"),
            create_price("09:10"),
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    loaded_prices = repository.read(
        code="7203",
        interval_minutes=5,
        start_at=datetime(
            2026,
            7,
            13,
            9,
            5,
        ),
        end_at=datetime(
            2026,
            7,
            13,
            9,
            10,
        ),
    )

    assert len(loaded_prices) == 2
    assert loaded_prices[0].datetime.minute == 5
    assert loaded_prices[1].datetime.minute == 10


def test_repository_returns_latest_datetime(
    tmp_path: Path,
) -> None:
    """指定銘柄・時間軸の最新保存日時を返す。"""

    repository = create_repository(tmp_path)

    repository.save_all(
        prices=[
            create_price("09:00"),
            create_price("09:10"),
            create_price("09:05"),
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    latest = repository.latest_datetime(
        code="7203",
        interval_minutes=5,
    )

    assert latest == datetime(
        2026,
        7,
        13,
        9,
        10,
    )


def test_repository_returns_earliest_datetime(
    tmp_path: Path,
) -> None:
    """指定銘柄・時間軸の最古保存日時を返す。"""

    repository = create_repository(tmp_path)

    repository.save_all(
        prices=[
            create_price("09:10"),
            create_price("09:00"),
            create_price("09:05"),
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    earliest = repository.earliest_datetime(
        code="7203",
        interval_minutes=5,
    )

    assert earliest == datetime(
        2026,
        7,
        13,
        9,
        0,
    )


def test_repository_returns_none_without_bars(
    tmp_path: Path,
) -> None:
    """保存データがなければ最古・最新日時はNoneを返す。"""

    repository = create_repository(tmp_path)

    assert (
        repository.latest_datetime(
            code="7203",
            interval_minutes=5,
        )
        is None
    )

    assert (
        repository.earliest_datetime(
            code="7203",
            interval_minutes=5,
        )
        is None
    )


def test_repository_separates_latest_datetime_by_code(
    tmp_path: Path,
) -> None:
    """銘柄ごとに最新日時を分けて取得する。"""

    repository = create_repository(tmp_path)

    repository.save_all(
        prices=[
            create_price(
                "09:00",
                code="7203",
            ),
            create_price(
                "09:10",
                code="7203",
            ),
            create_price(
                "09:05",
                code="8306",
            ),
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    assert repository.latest_datetime(
        code="7203",
        interval_minutes=5,
    ) == datetime(
        2026,
        7,
        13,
        9,
        10,
    )

    assert repository.latest_datetime(
        code="8306",
        interval_minutes=5,
    ) == datetime(
        2026,
        7,
        13,
        9,
        5,
    )


def test_repository_separates_latest_datetime_by_interval(
    tmp_path: Path,
) -> None:
    """時間軸ごとに最新日時を分けて取得する。"""

    repository = create_repository(tmp_path)

    repository.save_all(
        prices=[create_price("09:10")],
        interval_minutes=1,
        data_source="jquants",
    )

    repository.save_all(
        prices=[create_price("09:05")],
        interval_minutes=5,
        data_source="jquants",
    )

    assert repository.latest_datetime(
        code="7203",
        interval_minutes=1,
    ) == datetime(
        2026,
        7,
        13,
        9,
        10,
    )

    assert repository.latest_datetime(
        code="7203",
        interval_minutes=5,
    ) == datetime(
        2026,
        7,
        13,
        9,
        5,
    )


def test_repository_accepts_empty_list(
    tmp_path: Path,
) -> None:
    """空の一覧は保存0件として扱う。"""

    repository = create_repository(tmp_path)

    saved_count = repository.save_all(
        prices=[],
        interval_minutes=5,
        data_source="jquants",
    )

    assert saved_count == 0
    assert repository.count() == 0


@pytest.mark.parametrize(
    ("interval_minutes", "data_source", "message"),
    [
        (0, "jquants", "時間足"),
        (-1, "jquants", "時間足"),
        (5, "", "データソース"),
    ],
)
def test_repository_rejects_invalid_save_arguments(
    tmp_path: Path,
    interval_minutes: int,
    data_source: str,
    message: str,
) -> None:
    """不正な保存条件を拒否する。"""

    repository = create_repository(tmp_path)

    with pytest.raises(ValueError, match=message):
        repository.save_all(
            prices=[create_price("09:00")],
            interval_minutes=interval_minutes,
            data_source=data_source,
        )


def test_repository_rejects_reversed_date_range(
    tmp_path: Path,
) -> None:
    """開始日時が終了日時より後なら拒否する。"""

    repository = create_repository(tmp_path)

    with pytest.raises(
        ValueError,
        match="開始日時",
    ):
        repository.read(
            code="7203",
            interval_minutes=5,
            start_at=datetime(
                2026,
                7,
                13,
                10,
                0,
            ),
            end_at=datetime(
                2026,
                7,
                13,
                9,
                0,
            ),
        )


@pytest.mark.parametrize(
    "method_name",
    [
        "latest_datetime",
        "earliest_datetime",
    ],
)
def test_repository_datetime_methods_reject_empty_code(
    tmp_path: Path,
    method_name: str,
) -> None:
    """最古・最新日時取得で空の銘柄コードを拒否する。"""

    repository = create_repository(tmp_path)
    method = getattr(repository, method_name)

    with pytest.raises(
        ValueError,
        match="銘柄コード",
    ):
        method(
            code="",
            interval_minutes=5,
        )


@pytest.mark.parametrize(
    "method_name",
    [
        "latest_datetime",
        "earliest_datetime",
    ],
)
def test_repository_datetime_methods_reject_invalid_interval(
    tmp_path: Path,
    method_name: str,
) -> None:
    """最古・最新日時取得で不正な時間軸を拒否する。"""

    repository = create_repository(tmp_path)
    method = getattr(repository, method_name)

    with pytest.raises(
        ValueError,
        match="時間足",
    ):
        method(
            code="7203",
            interval_minutes=0,
        )
