"""J-Quantsの履歴分足を期間分割して取り込む処理。"""

from collections.abc import Callable
from datetime import date
from typing import Protocol

from app.market.date_range import (
    filter_date_range,
    split_dates,
)
from app.market.history_progress import (
    HistoryImportFailure,
    HistoryImportProgress,
    HistoryImportResult,
    HistorySymbolResult,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
)


class TradingCalendarReader(Protocol):
    """取引カレンダー取得処理のインターフェース。"""

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """指定期間の営業日一覧を返す。"""


class HistoricalBatchImporter(Protocol):
    """営業日を指定できる一括取込処理。"""

    def run_dates(
        self,
        codes: list[str],
        target_dates: list[date],
        *,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: object | None = None,
    ) -> JQuantsBatchImportResult:
        """指定銘柄・日付の市場データを取り込む。"""


HistoryProgressCallback = Callable[
    [HistoryImportProgress],
    None,
]


class JQuantsHistoryImporter:
    """J-Quantsの履歴分足を分割してSQLiteへ取り込む。"""

    def __init__(
        self,
        calendar_reader: TradingCalendarReader,
        batch_importer: HistoricalBatchImporter,
    ) -> None:
        """営業日取得処理と一括取込処理を受け取る。"""

        self.calendar_reader = calendar_reader
        self.batch_importer = batch_importer

    def run(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
        *,
        chunk_business_days: int = 20,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: (HistoryProgressCallback | None) = None,
    ) -> HistoryImportResult:
        """複数銘柄の履歴データを期間分割して取り込む。"""

        normalized_codes = self._normalize_codes(codes)

        if start_date > end_date:
            raise ValueError("開始日は終了日以前にしてください。")

        if chunk_business_days <= 0:
            raise ValueError("チャンク営業日数は0より大きい必要があります。")

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if not data_source.strip():
            raise ValueError("データソースを指定してください。")

        business_dates = self.calendar_reader.get_business_dates(
            start_date=start_date,
            end_date=end_date,
        )

        business_dates = filter_date_range(
            target_dates=business_dates,
            start_date=start_date,
            end_date=end_date,
        )

        date_chunks = split_dates(
            target_dates=business_dates,
            chunk_size=chunk_business_days,
        )

        total_tasks = len(normalized_codes) * len(date_chunks)
        completed_tasks = 0

        symbol_results: list[HistorySymbolResult] = []
        failures: list[HistoryImportFailure] = []

        for code in normalized_codes:
            symbol_request_count = 0
            symbol_successful_count = 0
            symbol_empty_count = 0
            symbol_failed_count = 0

            symbol_minute_bar_count = 0
            symbol_five_minute_bar_count = 0
            symbol_processed_bar_count = 0

            for chunk_number, target_dates in enumerate(
                date_chunks,
                start=1,
            ):
                chunk_start = target_dates[0]
                chunk_end = target_dates[-1]

                try:
                    batch_result = self.batch_importer.run_dates(
                        codes=[code],
                        target_dates=target_dates,
                        interval_minutes=(interval_minutes),
                        data_source=data_source,
                        continue_on_error=(continue_on_error),
                    )

                except Exception as error:
                    if not continue_on_error:
                        raise

                    failed_count = len(target_dates)

                    batch_result = self._create_failed_batch_result(
                        date_count=len(target_dates),
                        failed_count=failed_count,
                    )

                    failures.append(
                        HistoryImportFailure(
                            code=code,
                            start_date=chunk_start,
                            end_date=chunk_end,
                            message=str(error),
                        )
                    )

                symbol_request_count += batch_result.request_count
                symbol_successful_count += batch_result.successful_request_count
                symbol_empty_count += batch_result.empty_request_count
                symbol_failed_count += batch_result.failed_request_count

                symbol_minute_bar_count += batch_result.minute_bar_count
                symbol_five_minute_bar_count += batch_result.five_minute_bar_count
                symbol_processed_bar_count += batch_result.processed_bar_count

                for failure in batch_result.failures:
                    failures.append(
                        HistoryImportFailure(
                            code=failure.code,
                            start_date=(failure.target_date),
                            end_date=(failure.target_date),
                            message=failure.message,
                        )
                    )

                completed_tasks += 1

                if progress_callback is not None:
                    progress_callback(
                        HistoryImportProgress(
                            completed_tasks=(completed_tasks),
                            total_tasks=total_tasks,
                            code=code,
                            chunk_number=chunk_number,
                            chunk_count=len(date_chunks),
                            start_date=chunk_start,
                            end_date=chunk_end,
                            request_count=(batch_result.request_count),
                            successful_request_count=(
                                batch_result.successful_request_count
                            ),
                            empty_request_count=(batch_result.empty_request_count),
                            failed_request_count=(batch_result.failed_request_count),
                            minute_bar_count=(batch_result.minute_bar_count),
                            five_minute_bar_count=(batch_result.five_minute_bar_count),
                            processed_bar_count=(batch_result.processed_bar_count),
                        )
                    )

            symbol_results.append(
                HistorySymbolResult(
                    code=code,
                    business_date_count=len(business_dates),
                    chunk_count=len(date_chunks),
                    request_count=symbol_request_count,
                    successful_request_count=(symbol_successful_count),
                    empty_request_count=(symbol_empty_count),
                    failed_request_count=(symbol_failed_count),
                    minute_bar_count=(symbol_minute_bar_count),
                    five_minute_bar_count=(symbol_five_minute_bar_count),
                    processed_bar_count=(symbol_processed_bar_count),
                )
            )

        return HistoryImportResult(
            start_date=start_date,
            end_date=end_date,
            code_results=symbol_results,
            failures=failures,
        )

    @staticmethod
    def _create_failed_batch_result(
        date_count: int,
        failed_count: int,
    ) -> JQuantsBatchImportResult:
        """チャンク全体が失敗した場合の結果を作成する。"""

        return JQuantsBatchImportResult(
            code_count=1,
            date_count=date_count,
            request_count=failed_count,
            successful_request_count=0,
            empty_request_count=0,
            failed_request_count=failed_count,
            minute_bar_count=0,
            five_minute_bar_count=0,
            processed_bar_count=0,
            failures=[],
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
