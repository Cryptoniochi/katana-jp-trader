"""SQLiteの保存状況に基づく市場データ差分更新処理。"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from app.market.bar_repository import MarketBarRepository
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
)


class BatchImportRunner(Protocol):
    """一括取込サービスが満たすインターフェース。"""

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
        """指定した銘柄・期間を取り込む。"""


@dataclass(frozen=True, slots=True)
class IncrementalCodeUpdateResult:
    """1銘柄分の差分更新結果。"""

    code: str
    start_date: date | None
    end_date: date
    previous_latest_date: date | None
    skipped: bool

    request_count: int
    successful_request_count: int
    empty_request_count: int
    failed_request_count: int

    minute_bar_count: int
    five_minute_bar_count: int
    processed_bar_count: int


@dataclass(frozen=True, slots=True)
class IncrementalMarketUpdateResult:
    """複数銘柄の差分更新結果。"""

    code_results: list[IncrementalCodeUpdateResult]

    @property
    def code_count(self) -> int:
        """対象銘柄数を返す。"""

        return len(self.code_results)

    @property
    def updated_code_count(self) -> int:
        """API取得を実行した銘柄数を返す。"""

        return sum(1 for result in self.code_results if not result.skipped)

    @property
    def skipped_code_count(self) -> int:
        """更新不要でスキップした銘柄数を返す。"""

        return sum(1 for result in self.code_results if result.skipped)

    @property
    def request_count(self) -> int:
        """APIリクエスト総数を返す。"""

        return sum(result.request_count for result in self.code_results)

    @property
    def successful_request_count(self) -> int:
        """データ取得に成功したリクエスト総数を返す。"""

        return sum(result.successful_request_count for result in self.code_results)

    @property
    def empty_request_count(self) -> int:
        """データ0件だったリクエスト総数を返す。"""

        return sum(result.empty_request_count for result in self.code_results)

    @property
    def failed_request_count(self) -> int:
        """失敗したリクエスト総数を返す。"""

        return sum(result.failed_request_count for result in self.code_results)

    @property
    def minute_bar_count(self) -> int:
        """取得した1分足総数を返す。"""

        return sum(result.minute_bar_count for result in self.code_results)

    @property
    def five_minute_bar_count(self) -> int:
        """生成した5分足総数を返す。"""

        return sum(result.five_minute_bar_count for result in self.code_results)

    @property
    def processed_bar_count(self) -> int:
        """SQLiteへ処理した時間足総数を返す。"""

        return sum(result.processed_bar_count for result in self.code_results)


class IncrementalMarketUpdateService:
    """銘柄ごとの最新保存日を基準に差分更新する。"""

    def __init__(
        self,
        repository: MarketBarRepository,
        batch_importer: BatchImportRunner,
    ) -> None:
        """Repositoryと一括取込サービスを受け取る。"""

        self.repository = repository
        self.batch_importer = batch_importer

    def run(
        self,
        codes: list[str],
        initial_start_date: date,
        end_date: date,
        *,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
    ) -> IncrementalMarketUpdateResult:
        """銘柄ごとに不足期間だけを取得する。"""

        normalized_codes = self._normalize_codes(codes)

        if initial_start_date > end_date:
            raise ValueError("初回開始日は終了日以前にしてください。")

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if not data_source.strip():
            raise ValueError("データソースを指定してください。")

        code_results: list[IncrementalCodeUpdateResult] = []

        for code in normalized_codes:
            latest_datetime = self.repository.latest_datetime(
                code=code,
                interval_minutes=interval_minutes,
            )

            previous_latest_date = (
                latest_datetime.date() if latest_datetime is not None else None
            )

            if previous_latest_date is None:
                update_start_date = initial_start_date
            else:
                update_start_date = previous_latest_date + timedelta(days=1)

            if update_start_date > end_date:
                code_results.append(
                    IncrementalCodeUpdateResult(
                        code=code,
                        start_date=None,
                        end_date=end_date,
                        previous_latest_date=previous_latest_date,
                        skipped=True,
                        request_count=0,
                        successful_request_count=0,
                        empty_request_count=0,
                        failed_request_count=0,
                        minute_bar_count=0,
                        five_minute_bar_count=0,
                        processed_bar_count=0,
                    )
                )
                continue

            batch_result = self.batch_importer.run(
                codes=[code],
                start_date=update_start_date,
                end_date=end_date,
                interval_minutes=interval_minutes,
                data_source=data_source,
                continue_on_error=continue_on_error,
            )

            code_results.append(
                IncrementalCodeUpdateResult(
                    code=code,
                    start_date=update_start_date,
                    end_date=end_date,
                    previous_latest_date=previous_latest_date,
                    skipped=False,
                    request_count=batch_result.request_count,
                    successful_request_count=(batch_result.successful_request_count),
                    empty_request_count=(batch_result.empty_request_count),
                    failed_request_count=(batch_result.failed_request_count),
                    minute_bar_count=(batch_result.minute_bar_count),
                    five_minute_bar_count=(batch_result.five_minute_bar_count),
                    processed_bar_count=(batch_result.processed_bar_count),
                )
            )

        return IncrementalMarketUpdateResult(code_results=code_results)

    @staticmethod
    def _normalize_codes(
        codes: list[str],
    ) -> list[str]:
        """銘柄コードを検証し、重複を除去する。"""

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
