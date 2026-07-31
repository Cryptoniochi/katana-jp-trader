"""日足データから新高値ブレイク候補を抽出・保存する。"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.market.bar_repository import MarketBarRepository
from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateRepository,
)
from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
)
from app.strategy.high_breakout_screener import (
    HighBreakoutScreener,
)


JST = ZoneInfo("Asia/Tokyo")
DAILY_INTERVAL_MINUTES = 1440


class HighBreakoutScreeningInputError(ValueError):
    """新高値スクリーニング入力が不正であることを表す。"""


class HighBreakoutScreeningService:
    """日足系列の読込、候補抽出、候補保存を統括する。"""

    def __init__(
        self,
        *,
        screener: HighBreakoutScreener,
        candidate_repository: HighBreakoutCandidateRepository,
    ) -> None:
        self.screener = screener
        self.candidate_repository = candidate_repository

    def run_from_database(
        self,
        *,
        market_bar_repository: MarketBarRepository,
        codes: Iterable[str],
    ) -> tuple[HighBreakoutCandidate, ...]:
        """SQLiteの1440分足を読み込み候補を保存する。"""

        series_collection: list[HistoricalBarSeries] = []

        for raw_code in codes:
            code = self._normalize_code(raw_code)
            prices = market_bar_repository.read(
                code=code,
                interval_minutes=DAILY_INTERVAL_MINUTES,
            )

            if not prices:
                continue

            bars = tuple(
                HistoricalBar(
                    code=price.code,
                    timeframe=MarketTimeframe.DAY_1,
                    opened_at=self._normalize_datetime(
                        price.datetime
                    ),
                    open_price=price.open,
                    high_price=price.high,
                    low_price=price.low,
                    close_price=price.close,
                    volume=float(price.volume),
                )
                for price in prices
            )
            series_collection.append(
                HistoricalBarSeries(
                    code=code,
                    timeframe=MarketTimeframe.DAY_1,
                    bars=bars,
                )
            )

        return self._screen_and_save(
            series_collection
        )

    def run_from_csv(
        self,
        csv_path: Path,
    ) -> tuple[HighBreakoutCandidate, ...]:
        """CSVの日足データを読み込み候補を保存する。"""

        path = Path(csv_path)

        if not path.exists():
            raise HighBreakoutScreeningInputError(
                "CSVファイルが存在しません。 "
                f"path={path}"
            )

        grouped: dict[str, list[HistoricalBar]] = defaultdict(list)

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            reader = csv.DictReader(stream)
            required = {
                "code",
                "traded_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
            }

            if reader.fieldnames is None:
                raise HighBreakoutScreeningInputError(
                    "CSVヘッダーがありません。"
                )

            missing = required - set(reader.fieldnames)

            if missing:
                raise HighBreakoutScreeningInputError(
                    "CSV必須列が不足しています。 "
                    f"columns={','.join(sorted(missing))}"
                )

            for row_number, row in enumerate(
                reader,
                start=2,
            ):
                try:
                    code = self._normalize_code(
                        row["code"]
                    )
                    opened_at = self._normalize_datetime(
                        datetime.fromisoformat(
                            row["traded_at"]
                        )
                    )
                    bar = HistoricalBar(
                        code=code,
                        timeframe=MarketTimeframe.DAY_1,
                        opened_at=opened_at,
                        open_price=float(row["open"]),
                        high_price=float(row["high"]),
                        low_price=float(row["low"]),
                        close_price=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ) as error:
                    raise HighBreakoutScreeningInputError(
                        "CSV行を日足へ変換できません。 "
                        f"line={row_number}"
                    ) from error

                grouped[code].append(bar)

        series_collection = tuple(
            HistoricalBarSeries(
                code=code,
                timeframe=MarketTimeframe.DAY_1,
                bars=tuple(
                    sorted(
                        bars,
                        key=lambda item: item.opened_at,
                    )
                ),
            )
            for code, bars in sorted(grouped.items())
        )

        return self._screen_and_save(
            series_collection
        )

    def _screen_and_save(
        self,
        series_collection: Iterable[
            HistoricalBarSeries
        ],
    ) -> tuple[HighBreakoutCandidate, ...]:
        candidates = self.screener.screen_many(
            series_collection
        )
        self.candidate_repository.save_all(
            candidates
        )
        return candidates

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        normalized = code.strip()

        if not normalized:
            raise HighBreakoutScreeningInputError(
                "銘柄コードを指定してください。"
            )

        if not normalized.isdigit():
            raise HighBreakoutScreeningInputError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {4, 5}:
            raise HighBreakoutScreeningInputError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=JST)

        return value.astimezone(JST)
