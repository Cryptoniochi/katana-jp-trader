"""J-Quants分足を複数銘柄・複数日まとめて取り込む処理。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from time import sleep
from typing import Protocol

from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.jquants_downloader import JQuantsDownloadError
from app.market.models import StockPrice


class MinutePriceDownloader(Protocol):
    """1分足Downloaderが満たすインターフェース。"""

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """指定銘柄・日付の1分足を返す。"""


@dataclass(frozen=True, slots=True)
class JQuantsImportFailure:
    """取得に失敗した銘柄・日付と理由。"""

    code: str
    target_date: date
    message: str


@dataclass(frozen=True, slots=True)
class JQuantsBatchImportResult:
    """複数銘柄・複数日の一括取込結果。"""

    code_count: int
    date_count: int
    request_count: int

    successful_request_count: int
    empty_request_count: int
    failed_request_count: int

    minute_bar_count: int
    five_minute_bar_count: int
    processed_bar_count: int

    failures: list[JQuantsImportFailure]


ProgressCallback = Callable[
    [
        int,
        int,
        str,
        date,
        int,
        int,
    ],
    None,
]


class JQuantsBatchImportService:
    """J-Quants分足を5分足へ変換してSQLiteへ保存する。"""

    def __init__(
        self,
        downloader: MinutePriceDownloader,
        aggregator: StockPriceAggregator,
        repository: MarketBarRepository,
        request_interval_seconds: float = 1.1,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        """必要な構成要素とリクエスト間隔を設定する。"""

        if request_interval_seconds < 0:
            raise ValueError("リクエスト間隔は0秒以上で指定してください。")

        self.downloader = downloader
        self.aggregator = aggregator
        self.repository = repository
        self.request_interval_seconds = request_interval_seconds
        self.sleeper = sleeper

    def run(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
        *,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> JQuantsBatchImportResult:
        """カレンダー日単位で指定期間を取り込む。"""

        if start_date > end_date:
            raise ValueError("開始日は終了日以前にしてください。")

        target_dates = self._create_date_range(
            start_date=start_date,
            end_date=end_date,
        )

        return self.run_dates(
            codes=codes,
            target_dates=target_dates,
            interval_minutes=interval_minutes,
            data_source=data_source,
            continue_on_error=continue_on_error,
            progress_callback=progress_callback,
        )

    def run_dates(
        self,
        codes: list[str],
        target_dates: list[date],
        *,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> JQuantsBatchImportResult:
        """明示された日付だけを取り込む。"""

        normalized_codes = self._normalize_codes(codes)
        normalized_dates = sorted(set(target_dates))

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if not data_source.strip():
            raise ValueError("データソースを指定してください。")

        total_requests = len(normalized_codes) * len(normalized_dates)

        request_count = 0
        successful_request_count = 0
        empty_request_count = 0

        minute_bar_count = 0
        five_minute_bar_count = 0
        processed_bar_count = 0

        failures: list[JQuantsImportFailure] = []

        for code in normalized_codes:
            for target_date in normalized_dates:
                request_count += 1
                current_minute_count = 0

                try:
                    minute_prices = self.downloader.download(
                        code=code,
                        date=target_date.isoformat(),
                    )

                    current_minute_count = len(minute_prices)

                    if not minute_prices:
                        empty_request_count += 1
                    else:
                        successful_request_count += 1
                        minute_bar_count += current_minute_count

                        aggregated_prices = self.aggregator.aggregate(
                            prices=minute_prices,
                            interval_minutes=(interval_minutes),
                        )

                        five_minute_bar_count += len(aggregated_prices)

                        processed_bar_count += self.repository.save_all(
                            prices=aggregated_prices,
                            interval_minutes=(interval_minutes),
                            data_source=data_source,
                        )

                except (
                    JQuantsDownloadError,
                    ValueError,
                ) as error:
                    failures.append(
                        JQuantsImportFailure(
                            code=code,
                            target_date=target_date,
                            message=str(error),
                        )
                    )

                    if not continue_on_error:
                        raise

                if progress_callback is not None:
                    progress_callback(
                        request_count,
                        total_requests,
                        code,
                        target_date,
                        current_minute_count,
                        len(failures),
                    )

                if request_count < total_requests:
                    self.sleeper(self.request_interval_seconds)

        return JQuantsBatchImportResult(
            code_count=len(normalized_codes),
            date_count=len(normalized_dates),
            request_count=request_count,
            successful_request_count=(successful_request_count),
            empty_request_count=empty_request_count,
            failed_request_count=len(failures),
            minute_bar_count=minute_bar_count,
            five_minute_bar_count=five_minute_bar_count,
            processed_bar_count=processed_bar_count,
            failures=failures,
        )

    @staticmethod
    def _normalize_codes(
        codes: list[str],
    ) -> list[str]:
        """銘柄コードを検証して重複を除去する。"""

        if not codes:
            raise ValueError("銘柄コードを1件以上指定してください。")

        normalized_codes: list[str] = []

        for code in codes:
            normalized = code.strip()

            if not normalized.isdigit():
                raise ValueError("銘柄コードは数字で指定してください。")

            if len(normalized) not in (4, 5):
                raise ValueError("銘柄コードは4桁または5桁で指定してください。")

            if normalized not in normalized_codes:
                normalized_codes.append(normalized)

        return normalized_codes

    @staticmethod
    def _create_date_range(
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """開始日から終了日までの日付一覧を返す。"""

        number_of_days = (end_date - start_date).days

        return [
            start_date + timedelta(days=offset) for offset in range(number_of_days + 1)
        ]
