"""kabuステーションBoard APIから候補ユニバースの日足を収集する。"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.market.kabu_station_client import KabuStationClient
from app.market.kabu_station_models import KabuStationSymbol
from app.universe.universe_daily_bar_models import (
    UniverseDailyBar,
)
from app.universe.universe_daily_bar_repository import (
    UniverseDailyBarRepository,
)


Sleeper = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class UniverseDailyCollectionFailure:
    """1銘柄の日足収集失敗。"""

    code: str
    error_type: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class UniverseDailyCollectionResult:
    """候補ユニバース日足の収集結果。"""

    generated_at: datetime
    trading_date: date
    requested_count: int
    collected_count: int
    saved_count: int
    skipped_count: int
    failures: tuple[UniverseDailyCollectionFailure, ...]
    source_name: str

    @property
    def success_ratio(self) -> float:
        if self.requested_count <= 0:
            return 0.0
        return self.collected_count / self.requested_count

    @property
    def completed(self) -> bool:
        return (
            self.requested_count > 0
            and self.collected_count > 0
            and self.saved_count == self.collected_count
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "requested_count": self.requested_count,
            "collected_count": self.collected_count,
            "saved_count": self.saved_count,
            "skipped_count": self.skipped_count,
            "failure_count": len(self.failures),
            "success_ratio": round(self.success_ratio, 6),
            "completed": self.completed,
            "source_name": self.source_name,
            "failures": [
                failure.to_dict()
                for failure in self.failures
            ],
        }


class KabuStationUniverseDailyBarCollector:
    """DB内候補コードをBoard APIで照会し、当日OHLCVを保存する。"""

    def __init__(
        self,
        *,
        client: KabuStationClient,
        database_path: Path,
        repository: UniverseDailyBarRepository | None = None,
        exchange: int = 1,
        source_name: str = "kabu-station-board-daily",
        request_interval_seconds: float = 0.12,
        minimum_success_ratio: float = 0.80,
        sleeper: Sleeper = time.sleep,
        now_provider=None,
    ) -> None:
        if request_interval_seconds < 0:
            raise ValueError(
                "API呼出し間隔は0以上である必要があります。"
            )
        if not 0 < minimum_success_ratio <= 1:
            raise ValueError(
                "最低成功率は0より大きく1以下である必要があります。"
            )

        self.client = client
        self.database_path = Path(database_path)
        self.repository = (
            repository
            if repository is not None
            else UniverseDailyBarRepository(
                self.database_path
            )
        )
        self.exchange = int(exchange)
        self.source_name = source_name.strip()
        self.request_interval_seconds = (
            request_interval_seconds
        )
        self.minimum_success_ratio = (
            minimum_success_ratio
        )
        self.sleeper = sleeper
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def collect(
        self,
        *,
        trading_date: date,
        codes: Sequence[str] | None = None,
    ) -> UniverseDailyCollectionResult:
        """指定日の候補ユニバース日足を収集・保存する。"""

        resolved_codes = (
            self._load_universe_codes()
            if codes is None
            else self._normalize_codes(codes)
        )

        if not resolved_codes:
            raise RuntimeError(
                "日足収集対象の候補ユニバースが空です。"
            )

        self.client.issue_token()

        bars: list[UniverseDailyBar] = []
        failures: list[UniverseDailyCollectionFailure] = []
        skipped_count = 0

        for index, code in enumerate(resolved_codes):
            try:
                payload = self.client.board(
                    KabuStationSymbol(
                        code=code,
                        exchange=self.exchange,
                    )
                )
                bar = self._to_daily_bar(
                    code=code,
                    trading_date=trading_date,
                    payload=payload,
                )
                if bar is None:
                    skipped_count += 1
                else:
                    bars.append(bar)
            except Exception as error:
                failures.append(
                    UniverseDailyCollectionFailure(
                        code=code,
                        error_type=type(error).__name__,
                        message=(
                            str(error).strip()
                            or type(error).__name__
                        ),
                    )
                )

            if (
                index + 1 < len(resolved_codes)
                and self.request_interval_seconds > 0
            ):
                self.sleeper(
                    self.request_interval_seconds
                )

        saved_count = self.repository.upsert_many(
            tuple(bars)
        )

        result = UniverseDailyCollectionResult(
            generated_at=self._current_time(),
            trading_date=trading_date,
            requested_count=len(resolved_codes),
            collected_count=len(bars),
            saved_count=saved_count,
            skipped_count=skipped_count,
            failures=tuple(failures),
            source_name=self.source_name,
        )

        if result.success_ratio < self.minimum_success_ratio:
            raise RuntimeError(
                "候補ユニバース日足の収集成功率が"
                "基準を下回りました。 "
                f"requested={result.requested_count} "
                f"collected={result.collected_count} "
                f"ratio={result.success_ratio:.3f} "
                f"minimum={self.minimum_success_ratio:.3f}"
            )

        return result

    def _load_universe_codes(self) -> tuple[str, ...]:
        if not self.database_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.database_path}"
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT code
                FROM market_bars
                WHERE code IS NOT NULL
                  AND trim(code) <> ''
                ORDER BY code
                """
            ).fetchall()

        return self._normalize_codes(
            str(row[0])
            for row in rows
        )

    @staticmethod
    def _normalize_codes(
        codes: Sequence[str],
    ) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                normalized
                for value in codes
                if (
                    (normalized := str(value).strip())
                    and normalized.isdigit()
                    and len(normalized) in {4, 5}
                )
            )
        )

    def _to_daily_bar(
        self,
        *,
        code: str,
        trading_date: date,
        payload: dict[str, object],
    ) -> UniverseDailyBar | None:
        open_price = self._positive_float(
            payload.get("OpeningPrice")
        )
        high_price = self._positive_float(
            payload.get("HighPrice")
        )
        low_price = self._positive_float(
            payload.get("LowPrice")
        )
        close_price = self._positive_float(
            payload.get("CurrentPrice")
        )
        volume = self._nonnegative_int(
            payload.get("TradingVolume")
        )

        # 売買不成立・休止銘柄は日足を作らない。
        if (
            open_price is None
            or high_price is None
            or low_price is None
            or close_price is None
            or volume is None
            or volume <= 0
        ):
            return None

        if not (
            low_price
            <= min(open_price, close_price)
            <= max(open_price, close_price)
            <= high_price
        ):
            raise ValueError(
                "Board APIのOHLC関係が不正です。 "
                f"code={code}"
            )

        return UniverseDailyBar(
            code=code,
            trading_date=trading_date,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
            data_source=self.source_name,
        )

    @staticmethod
    def _positive_float(value: object) -> float | None:
        if value is None:
            return None
        normalized = float(value)
        return normalized if normalized > 0 else None

    @staticmethod
    def _nonnegative_int(value: object) -> int | None:
        if value is None:
            return None
        normalized = int(float(value))
        return normalized if normalized >= 0 else None

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return value.astimezone(timezone.utc)
