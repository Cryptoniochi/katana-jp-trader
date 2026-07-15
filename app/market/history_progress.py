"""J-Quants履歴データ取込の進捗情報。"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class HistoryImportProgress:
    """履歴取込の現在位置を表す。"""

    completed_tasks: int
    total_tasks: int

    code: str
    chunk_number: int
    chunk_count: int

    start_date: date
    end_date: date

    request_count: int
    successful_request_count: int
    empty_request_count: int
    failed_request_count: int

    minute_bar_count: int
    five_minute_bar_count: int
    processed_bar_count: int

    @property
    def completion_rate(self) -> float:
        """処理完了率を百分率で返す。"""

        if self.total_tasks <= 0:
            return 100.0

        return self.completed_tasks / self.total_tasks * 100.0


@dataclass(frozen=True, slots=True)
class HistoryImportFailure:
    """履歴取込に失敗した処理単位を表す。"""

    code: str
    start_date: date
    end_date: date
    message: str


@dataclass(frozen=True, slots=True)
class HistorySymbolResult:
    """1銘柄分の履歴取込結果。"""

    code: str
    business_date_count: int
    chunk_count: int

    request_count: int
    successful_request_count: int
    empty_request_count: int
    failed_request_count: int

    minute_bar_count: int
    five_minute_bar_count: int
    processed_bar_count: int


@dataclass(frozen=True, slots=True)
class HistoryImportResult:
    """履歴取込全体の結果。"""

    start_date: date
    end_date: date

    code_results: list[HistorySymbolResult]
    failures: list[HistoryImportFailure]

    @property
    def code_count(self) -> int:
        """対象銘柄数を返す。"""

        return len(self.code_results)

    @property
    def successful_code_count(self) -> int:
        """取得失敗がなかった銘柄数を返す。"""

        return sum(result.failed_request_count == 0 for result in self.code_results)

    @property
    def failed_code_count(self) -> int:
        """1件以上の取得失敗があった銘柄数を返す。"""

        return sum(result.failed_request_count > 0 for result in self.code_results)

    @property
    def business_date_count(self) -> int:
        """銘柄別営業日件数の合計を返す。"""

        return sum(result.business_date_count for result in self.code_results)

    @property
    def chunk_count(self) -> int:
        """処理したチャンク総数を返す。"""

        return sum(result.chunk_count for result in self.code_results)

    @property
    def request_count(self) -> int:
        """APIリクエスト総数を返す。"""

        return sum(result.request_count for result in self.code_results)

    @property
    def successful_request_count(self) -> int:
        """取得成功リクエスト総数を返す。"""

        return sum(result.successful_request_count for result in self.code_results)

    @property
    def empty_request_count(self) -> int:
        """データ0件のリクエスト総数を返す。"""

        return sum(result.empty_request_count for result in self.code_results)

    @property
    def failed_request_count(self) -> int:
        """取得失敗リクエスト総数を返す。"""

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
