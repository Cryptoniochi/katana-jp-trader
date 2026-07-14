"""moomoo OpenDから過去5分足を取得する。"""

from datetime import datetime

from moomoo import (
    RET_OK,
    AuType,
    KLType,
    OpenQuoteContext,
)

from app.market.models import StockPrice


class MoomooDownloadError(RuntimeError):
    """moomoo OpenAPIからの取得失敗を表す。"""


class MoomooHistoricalDownloader:
    """OpenDから過去5分足を取得するDownloader。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        page_size: int = 1000,
    ) -> None:
        """OpenDの接続先と1ページの取得件数を設定する。"""

        if not host:
            raise ValueError("OpenDのホストを指定してください。")

        if not 1 <= port <= 65535:
            raise ValueError("OpenDのポートは1～65535で指定してください。")

        if page_size <= 0:
            raise ValueError("1ページの取得件数は0より大きい必要があります。")

        self.host = host
        self.port = port
        self.page_size = page_size

    def download(
        self,
        code: str,
        start: str,
        end: str,
    ) -> list[StockPrice]:
        """指定銘柄・期間の過去5分足を取得する。"""

        if not code:
            raise ValueError("銘柄コードを指定してください。")

        self._validate_date(start)
        self._validate_date(end)

        if start > end:
            raise ValueError("開始日は終了日以前にしてください。")

        quote_context = OpenQuoteContext(
            host=self.host,
            port=self.port,
        )

        prices: list[StockPrice] = []
        page_req_key: bytes | None = None

        try:
            while True:
                return_code, data, page_req_key = quote_context.request_history_kline(
                    code=code,
                    start=start,
                    end=end,
                    ktype=KLType.K_5M,
                    autype=AuType.NONE,
                    max_count=self.page_size,
                    page_req_key=page_req_key,
                )

                if return_code != RET_OK:
                    raise MoomooDownloadError(
                        f"過去5分足の取得に失敗しました。 code={code} error={data}"
                    )

                prices.extend(self._convert_rows(data))

                if page_req_key is None:
                    break

        finally:
            quote_context.close()

        unique_prices = {(price.code, price.datetime): price for price in prices}

        return sorted(
            unique_prices.values(),
            key=lambda price: (
                price.datetime,
                price.code,
            ),
        )

    @staticmethod
    def _convert_rows(data: object) -> list[StockPrice]:
        """moomooのDataFrameをStockPrice一覧へ変換する。"""

        if not hasattr(data, "iterrows"):
            raise MoomooDownloadError("moomooから想定外の形式が返されました。")

        prices: list[StockPrice] = []

        for _index, row in data.iterrows():
            raw_code = str(row["code"])
            normalized_code = raw_code.split(".")[-1]

            prices.append(
                StockPrice(
                    code=normalized_code,
                    datetime=datetime.strptime(
                        str(row["time_key"]),
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row["volume"])),
                )
            )

        return prices

    @staticmethod
    def _validate_date(value: str) -> None:
        """YYYY-MM-DD形式の日付か確認する。"""

        try:
            datetime.strptime(
                value,
                "%Y-%m-%d",
            )
        except ValueError as error:
            raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error
