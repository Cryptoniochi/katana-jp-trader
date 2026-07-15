"""市場データ差分更新サービスのテスト。"""

from datetime import date, datetime
from pathlib import Path

import pytest

from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.incremental_update import (
    IncrementalMarketUpdateService,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
)
from app.market.models import StockPrice


class FakeBatchImporter:
    """呼び出し条件を記録する一括取込サービス。"""

    def __init__(self) -> None:
        """呼び出し履歴を初期化する。"""

        self.calls: list[tuple[list[str], date, date, int, str, bool]] = []

    def run(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
        *,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: object | None = None,
    ) -> JQuantsBatchImportResult:
        """固定の取込結果を返す。"""

        del progress_callback

        self.calls.append(
            (
                codes,
                start_date,
                end_date,
                interval_minutes,
                data_source,
                continue_on_error,
            )
        )

        return JQuantsBatchImportResult(
            code_count=len(codes),
            date_count=(end_date - start_date).days + 1,
            request_count=(len(codes) * ((end_date - start_date).days + 1)),
            successful_request_count=1,
            empty_request_count=0,
            failed_request_count=0,
            minute_bar_count=327,
            five_minute_bar_count=67,
            processed_bar_count=67,
            failures=[],
        )


def create_repository(
    tmp_path: Path,
) -> MarketBarRepository:
    """初期化済みRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return MarketBarRepository(database_path)


def create_price(
    code: str,
    date_text: str,
    time_text: str = "15:30",
) -> StockPrice:
    """最新日時確認用の5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=1000.0,
        high=1010.0,
        low=995.0,
        close=1005.0,
        volume=100_000,
    )


def test_service_starts_day_after_latest_date(
    tmp_path: Path,
) -> None:
    """最新保存日の翌日から更新する。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    repository.save_all(
        prices=[
            create_price(
                code="7203",
                date_text="2026-07-13",
            )
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    service = IncrementalMarketUpdateService(
        repository=repository,
        batch_importer=importer,
    )

    result = service.run(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
    )

    assert len(importer.calls) == 1
    assert importer.calls[0][0] == ["7203"]
    assert importer.calls[0][1] == date(
        2026,
        7,
        14,
    )
    assert importer.calls[0][2] == date(
        2026,
        7,
        15,
    )

    code_result = result.code_results[0]

    assert code_result.previous_latest_date == date(
        2026,
        7,
        13,
    )
    assert code_result.start_date == date(
        2026,
        7,
        14,
    )
    assert not code_result.skipped


def test_service_uses_initial_date_without_saved_data(
    tmp_path: Path,
) -> None:
    """未保存銘柄は初回開始日から取得する。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    service = IncrementalMarketUpdateService(
        repository=repository,
        batch_importer=importer,
    )

    result = service.run(
        codes=["8306"],
        initial_start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
    )

    assert importer.calls[0][1] == date(
        2026,
        7,
        1,
    )
    assert importer.calls[0][2] == date(
        2026,
        7,
        3,
    )

    assert result.code_results[0].previous_latest_date is None


def test_service_skips_up_to_date_symbol(
    tmp_path: Path,
) -> None:
    """終了日まで保存済みならAPI取得しない。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    repository.save_all(
        prices=[
            create_price(
                code="7203",
                date_text="2026-07-15",
            )
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    result = IncrementalMarketUpdateService(
        repository=repository,
        batch_importer=importer,
    ).run(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
    )

    assert importer.calls == []
    assert result.updated_code_count == 0
    assert result.skipped_code_count == 1
    assert result.code_results[0].skipped
    assert result.code_results[0].start_date is None


def test_service_handles_different_latest_dates(
    tmp_path: Path,
) -> None:
    """銘柄ごとの最新保存日に応じて開始日を変える。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    repository.save_all(
        prices=[
            create_price(
                code="7203",
                date_text="2026-07-13",
            ),
            create_price(
                code="8306",
                date_text="2026-07-14",
            ),
        ],
        interval_minutes=5,
        data_source="jquants",
    )

    result = IncrementalMarketUpdateService(
        repository=repository,
        batch_importer=importer,
    ).run(
        codes=["7203", "8306"],
        initial_start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
    )

    assert len(importer.calls) == 2
    assert importer.calls[0][1] == date(
        2026,
        7,
        14,
    )
    assert importer.calls[1][1] == date(
        2026,
        7,
        15,
    )

    assert result.code_count == 2
    assert result.updated_code_count == 2
    assert result.skipped_code_count == 0


def test_service_aggregates_result_counts(
    tmp_path: Path,
) -> None:
    """銘柄ごとの取込件数を合計できる。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    result = IncrementalMarketUpdateService(
        repository=repository,
        batch_importer=importer,
    ).run(
        codes=["7203", "8306"],
        initial_start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert result.request_count == 2
    assert result.successful_request_count == 2
    assert result.minute_bar_count == 654
    assert result.five_minute_bar_count == 134
    assert result.processed_bar_count == 134


def test_service_removes_duplicate_codes(
    tmp_path: Path,
) -> None:
    """重複した銘柄コードを1回だけ更新する。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    result = IncrementalMarketUpdateService(
        repository=repository,
        batch_importer=importer,
    ).run(
        codes=["7203", "7203"],
        initial_start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert result.code_count == 1
    assert len(importer.calls) == 1


@pytest.mark.parametrize(
    ("codes", "initial_start_date", "end_date", "message"),
    [
        (
            [],
            date(2026, 7, 1),
            date(2026, 7, 15),
            "銘柄コード",
        ),
        (
            ["ABCD"],
            date(2026, 7, 1),
            date(2026, 7, 15),
            "数字",
        ),
        (
            ["7203"],
            date(2026, 7, 16),
            date(2026, 7, 15),
            "初回開始日",
        ),
    ],
)
def test_service_rejects_invalid_arguments(
    tmp_path: Path,
    codes: list[str],
    initial_start_date: date,
    end_date: date,
    message: str,
) -> None:
    """不正な銘柄または期間を拒否する。"""

    repository = create_repository(tmp_path)
    importer = FakeBatchImporter()

    with pytest.raises(ValueError, match=message):
        IncrementalMarketUpdateService(
            repository=repository,
            batch_importer=importer,
        ).run(
            codes=codes,
            initial_start_date=initial_start_date,
            end_date=end_date,
        )
