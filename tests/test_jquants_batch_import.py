"""J-Quants複数銘柄・複数日取込のテスト。"""

from datetime import date, datetime
from pathlib import Path

import pytest

from app.database import initialize_database
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.jquants_batch_import import (
    JQuantsBatchImportService,
)
from app.market.jquants_downloader import (
    JQuantsDownloadError,
)
from app.market.models import StockPrice


class FakeDownloader:
    """テスト用の分足Downloader。"""

    def __init__(
        self,
        responses: dict[
            tuple[str, str],
            list[StockPrice],
        ],
    ) -> None:
        """銘柄・日付別の応答を受け取る。"""

        self.responses = responses
        self.requests: list[tuple[str, str]] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """登録済みの応答を返す。"""

        self.requests.append((code, date))

        return self.responses.get(
            (code, date),
            [],
        )


class FailingDownloader:
    """必ず取得エラーを返すDownloader。"""

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """取得失敗を発生させる。"""

        raise JQuantsDownloadError(f"download failed: {code} {date}")


def create_minute_price(
    code: str,
    date_text: str,
    time_text: str,
    *,
    close: float,
    volume: int = 100,
) -> StockPrice:
    """テスト用1分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=volume,
    )


def create_repository(
    tmp_path: Path,
) -> MarketBarRepository:
    """初期化済みRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return MarketBarRepository(database_path)


def test_service_imports_multiple_codes_and_dates(
    tmp_path: Path,
) -> None:
    """複数銘柄・複数日のデータを保存できる。"""

    responses = {
        (
            "7203",
            "2026-07-13",
        ): [
            create_minute_price(
                "7203",
                "2026-07-13",
                "09:00",
                close=1000,
            ),
            create_minute_price(
                "7203",
                "2026-07-13",
                "09:01",
                close=1001,
            ),
        ],
        (
            "8306",
            "2026-07-14",
        ): [
            create_minute_price(
                "8306",
                "2026-07-14",
                "09:00",
                close=2000,
            )
        ],
    }

    downloader = FakeDownloader(responses)
    repository = create_repository(tmp_path)

    service = JQuantsBatchImportService(
        downloader=downloader,
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    result = service.run(
        codes=["7203", "8306"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 14),
    )

    assert result.code_count == 2
    assert result.date_count == 2
    assert result.request_count == 4

    assert result.successful_request_count == 2
    assert result.empty_request_count == 2
    assert result.failed_request_count == 0

    assert result.minute_bar_count == 3
    assert result.five_minute_bar_count == 2
    assert result.processed_bar_count == 2

    assert repository.count(interval_minutes=5) == 2


def test_service_removes_duplicate_codes(
    tmp_path: Path,
) -> None:
    """重複した銘柄コードを1回だけ処理する。"""

    downloader = FakeDownloader({})
    repository = create_repository(tmp_path)

    service = JQuantsBatchImportService(
        downloader=downloader,
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    result = service.run(
        codes=["7203", "7203"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert result.code_count == 1
    assert result.request_count == 1
    assert downloader.requests == [("7203", "2026-07-13")]


def test_service_continues_after_download_failure(
    tmp_path: Path,
) -> None:
    """continue_on_errorが有効なら失敗を記録して継続する。"""

    repository = create_repository(tmp_path)

    service = JQuantsBatchImportService(
        downloader=FailingDownloader(),
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    result = service.run(
        codes=["7203", "8306"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
        continue_on_error=True,
    )

    assert result.request_count == 2
    assert result.failed_request_count == 2
    assert len(result.failures) == 2
    assert result.processed_bar_count == 0


def test_service_stops_after_download_failure(
    tmp_path: Path,
) -> None:
    """continue_on_errorが無効なら取得失敗を再送出する。"""

    repository = create_repository(tmp_path)

    service = JQuantsBatchImportService(
        downloader=FailingDownloader(),
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(
        JQuantsDownloadError,
        match="download failed",
    ):
        service.run(
            codes=["7203"],
            start_date=date(2026, 7, 13),
            end_date=date(2026, 7, 13),
            continue_on_error=False,
        )


def test_service_calls_progress_callback(
    tmp_path: Path,
) -> None:
    """リクエストごとに進捗コールバックを呼び出す。"""

    repository = create_repository(tmp_path)
    downloader = FakeDownloader({})

    progress: list[tuple[int, int, str, date, int, int]] = []

    service = JQuantsBatchImportService(
        downloader=downloader,
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    service.run(
        codes=["7203"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 14),
        progress_callback=lambda *values: progress.append(values),
    )

    assert len(progress) == 2
    assert progress[0][0] == 1
    assert progress[0][1] == 2
    assert progress[1][0] == 2


@pytest.mark.parametrize(
    ("codes", "start_date", "end_date", "message"),
    [
        (
            [],
            date(2026, 7, 13),
            date(2026, 7, 13),
            "銘柄コード",
        ),
        (
            ["ABC"],
            date(2026, 7, 13),
            date(2026, 7, 13),
            "数字",
        ),
        (
            ["7203"],
            date(2026, 7, 14),
            date(2026, 7, 13),
            "開始日",
        ),
    ],
)
def test_service_rejects_invalid_arguments(
    tmp_path: Path,
    codes: list[str],
    start_date: date,
    end_date: date,
    message: str,
) -> None:
    """不正な銘柄または期間を拒否する。"""

    repository = create_repository(tmp_path)

    service = JQuantsBatchImportService(
        downloader=FakeDownloader({}),
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(ValueError, match=message):
        service.run(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )
