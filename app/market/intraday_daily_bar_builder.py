"""保存済み分足から東証日足を生成する。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice


JST = ZoneInfo("Asia/Tokyo")
DAILY_INTERVAL_MINUTES = 1440


@dataclass(frozen=True, slots=True)
class DailyBarBuildResult:
    """日足生成結果。"""

    code_count: int
    source_bar_count: int
    daily_bar_count: int
    saved_bar_count: int

    def __post_init__(self) -> None:
        for name, value in {
            "銘柄数": self.code_count,
            "元時間足数": self.source_bar_count,
            "日足数": self.daily_bar_count,
            "保存数": self.saved_bar_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )


class IntradayDailyBarBuilder:
    """SQLiteの分足を営業日ごとの日足へ集約する。"""

    def __init__(
        self,
        *,
        repository: MarketBarRepository,
        source_interval_minutes: int = 5,
        data_source: str = "kabu-station-aggregated-daily",
    ) -> None:
        if source_interval_minutes <= 0:
            raise ValueError(
                "元時間足の間隔は0より大きい必要があります。"
            )

        normalized_source = data_source.strip()

        if not normalized_source:
            raise ValueError(
                "データソースを指定してください。"
            )

        if source_interval_minutes == DAILY_INTERVAL_MINUTES:
            raise ValueError(
                "元時間足に日足を指定できません。"
            )

        self.repository = repository
        self.source_interval_minutes = source_interval_minutes
        self.data_source = normalized_source

    def build(
        self,
        *,
        codes: tuple[str, ...],
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> DailyBarBuildResult:
        """指定銘柄の分足を日足へ集約して保存する。"""

        normalized_codes = tuple(
            dict.fromkeys(
                self._normalize_code(code)
                for code in codes
            )
        )

        if not normalized_codes:
            raise ValueError(
                "銘柄コードを1件以上指定してください。"
            )

        all_daily: list[StockPrice] = []
        source_bar_count = 0

        for code in normalized_codes:
            prices = self.repository.read(
                code=code,
                interval_minutes=self.source_interval_minutes,
                start_at=start_at,
                end_at=end_at,
            )
            source_bar_count += len(prices)
            all_daily.extend(
                self._aggregate_code(
                    code=code,
                    prices=tuple(prices),
                )
            )

        saved = self.repository.save_all(
            prices=all_daily,
            interval_minutes=DAILY_INTERVAL_MINUTES,
            data_source=self.data_source,
        )

        return DailyBarBuildResult(
            code_count=len(normalized_codes),
            source_bar_count=source_bar_count,
            daily_bar_count=len(all_daily),
            saved_bar_count=saved,
        )

    @classmethod
    def _aggregate_code(
        cls,
        *,
        code: str,
        prices: tuple[StockPrice, ...],
    ) -> tuple[StockPrice, ...]:
        grouped: dict[
            date,
            list[StockPrice],
        ] = defaultdict(list)

        for price in prices:
            normalized_datetime = cls._normalize_datetime(
                price.datetime
            )
            grouped[
                normalized_datetime.date()
            ].append(
                StockPrice(
                    code=price.code,
                    datetime=normalized_datetime,
                    open=price.open,
                    high=price.high,
                    low=price.low,
                    close=price.close,
                    volume=price.volume,
                )
            )

        daily: list[StockPrice] = []

        for trading_date, bars in sorted(
            grouped.items()
        ):
            ordered = sorted(
                bars,
                key=lambda item: item.datetime,
            )

            if not ordered:
                continue

            daily.append(
                StockPrice(
                    code=code,
                    datetime=datetime.combine(
                        trading_date,
                        time.min,
                        tzinfo=JST,
                    ),
                    open=ordered[0].open,
                    high=max(
                        item.high
                        for item in ordered
                    ),
                    low=min(
                        item.low
                        for item in ordered
                    ),
                    close=ordered[-1].close,
                    volume=sum(
                        item.volume
                        for item in ordered
                    ),
                )
            )

        return tuple(daily)

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=JST)

        return value.astimezone(JST)

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        normalized = code.strip()

        if not normalized:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized
