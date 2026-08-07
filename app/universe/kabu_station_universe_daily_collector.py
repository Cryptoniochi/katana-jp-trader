"""kabuステーションBoard APIから候補ユニバースの日足を収集する。"""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.market.kabu_station_client import KabuStationClient
from app.market.kabu_station_models import KabuStationSymbol
from app.universe.universe_daily_bar_models import UniverseDailyBar
from app.universe.universe_daily_bar_repository import (
    UniverseDailyBarRepository,
)


Sleeper = Callable[[float], None]
ProgressReporter = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class UniverseDailyCollectionFailure:
    """1銘柄の日足収集失敗。"""

    code: str
    error_type: str
    message: str
    attempts: int

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "error_type": self.error_type,
            "message": self.message,
            "attempts": self.attempts,
        }


@dataclass(frozen=True, slots=True)
class UniverseDailyCollectionSkip:
    """Board応答に日足作成に必要な値がない銘柄。"""

    code: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class UniverseDailyCollectionResult:
    """候補ユニバース日足の収集結果。"""

    generated_at: datetime
    trading_date: date
    requested_count: int
    collected_count: int
    saved_count: int
    skips: tuple[UniverseDailyCollectionSkip, ...]
    failures: tuple[UniverseDailyCollectionFailure, ...]
    source_name: str
    minimum_success_ratio: float

    @property
    def skipped_count(self) -> int:
        return len(self.skips)

    @property
    def success_ratio(self) -> float:
        if self.requested_count <= 0:
            return 0.0
        return self.collected_count / self.requested_count

    @property
    def meets_minimum_success_ratio(self) -> bool:
        return self.success_ratio >= self.minimum_success_ratio

    @property
    def completed(self) -> bool:
        return (
            self.requested_count > 0
            and self.collected_count > 0
            and self.saved_count == self.collected_count
            and self.meets_minimum_success_ratio
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
            "minimum_success_ratio": self.minimum_success_ratio,
            "meets_minimum_success_ratio": (
                self.meets_minimum_success_ratio
            ),
            "completed": self.completed,
            "source_name": self.source_name,
            "skips": [item.to_dict() for item in self.skips],
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
        request_interval_seconds: float = 0.30,
        minimum_success_ratio: float = 0.80,
        maximum_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        registration_batch_size: int | None = None,
        sleeper: Sleeper = time.sleep,
        progress_reporter: ProgressReporter | None = None,
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
        if maximum_attempts <= 0:
            raise ValueError(
                "最大試行回数は1以上である必要があります。"
            )
        if retry_backoff_seconds < 0:
            raise ValueError(
                "再試行待機秒数は0以上である必要があります。"
            )

        self.client = client

        settings = getattr(
            client,
            "settings",
            None,
        )
        maximum_registered = int(
            getattr(
                settings,
                "maximum_registered_symbols",
                50,
            )
        )
        resolved_batch_size = (
            maximum_registered
            if registration_batch_size is None
            else int(registration_batch_size)
        )

        if resolved_batch_size <= 0:
            raise ValueError(
                "登録バッチサイズは1以上である必要があります。"
            )

        if resolved_batch_size > maximum_registered:
            raise ValueError(
                "登録バッチサイズがkabuステーションの"
                "登録上限を超えています。 "
                f"batch_size={resolved_batch_size} "
                f"maximum={maximum_registered}"
            )

        self.database_path = Path(database_path)
        self.repository = (
            repository
            if repository is not None
            else UniverseDailyBarRepository(self.database_path)
        )
        self.exchange = int(exchange)
        self.source_name = source_name.strip()
        self.request_interval_seconds = request_interval_seconds
        self.minimum_success_ratio = minimum_success_ratio
        self.maximum_attempts = int(maximum_attempts)
        self.retry_backoff_seconds = retry_backoff_seconds
        self.registration_batch_size = resolved_batch_size
        self._registration_supported = (
            callable(
                getattr(
                    self.client,
                    "register_symbols",
                    None,
                )
            )
            and callable(
                getattr(
                    self.client,
                    "unregister_all",
                    None,
                )
            )
        )
        self.sleeper = sleeper
        self.progress_reporter = (
            progress_reporter
            if progress_reporter is not None
            else lambda _message: None
        )
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
        skips: list[UniverseDailyCollectionSkip] = []

        total = len(resolved_codes)
        processed_counter = [0]

        try:
            if self._registration_supported:
                for batch_number, code_batch in enumerate(
                    self._batches(
                        resolved_codes,
                        self.registration_batch_size,
                    ),
                    start=1,
                ):
                    self.progress_reporter(
                        "Registering batch "
                        f"{batch_number}: "
                        f"count={len(code_batch)}"
                    )
                    self._collect_registered_batch(
                        trading_date=trading_date,
                        code_batch=code_batch,
                        bars=bars,
                        failures=failures,
                        skips=skips,
                        processed_counter=processed_counter,
                        total=total,
                    )
            else:
                for code in resolved_codes:
                    processed_counter[0] += 1
                    self._collect_one_unregistered(
                        code=code,
                        trading_date=trading_date,
                        bars=bars,
                        failures=failures,
                        skips=skips,
                    )

                    if (
                        processed_counter[0] < total
                        and self.request_interval_seconds > 0
                    ):
                        self.sleeper(
                            self.request_interval_seconds
                        )
        finally:
            if self._registration_supported:
                try:
                    self._unregister_all_with_retry()
                except Exception as error:
                    self.progress_reporter(
                        "WARNING: unregister_all failed: "
                        f"{type(error).__name__}: {error}"
                    )

        saved_count = self.repository.upsert_many(tuple(bars))

        result = UniverseDailyCollectionResult(
            generated_at=self._current_time(),
            trading_date=trading_date,
            requested_count=total,
            collected_count=len(bars),
            saved_count=saved_count,
            skips=tuple(skips),
            failures=tuple(failures),
            source_name=self.source_name,
            minimum_success_ratio=self.minimum_success_ratio,
        )

        if (
            not self._registration_supported
            and not result.meets_minimum_success_ratio
        ):
            raise RuntimeError(
                "候補ユニバース日足の収集成功率が"
                "基準を下回りました。 "
                f"requested={result.requested_count} "
                f"collected={result.collected_count} "
                f"ratio={result.success_ratio:.3f} "
                f"minimum={result.minimum_success_ratio:.3f}"
            )

        return result

    def _collect_registered_batch(
        self,
        *,
        trading_date: date,
        code_batch: tuple[str, ...],
        bars: list[UniverseDailyBar],
        failures: list[UniverseDailyCollectionFailure],
        skips: list[UniverseDailyCollectionSkip],
        processed_counter: list[int],
        total: int,
    ) -> None:
        """登録不能銘柄を二分探索的に分離しつつ収集する。"""

        if not code_batch:
            return

        symbols = tuple(
            KabuStationSymbol(
                code=code,
                exchange=self.exchange,
            )
            for code in code_batch
        )

        try:
            self._register_batch(symbols)
        except Exception as error:
            if len(code_batch) == 1:
                code = code_batch[0]
                processed_counter[0] += 1
                failures.append(
                    UniverseDailyCollectionFailure(
                        code=code,
                        error_type=type(error).__name__,
                        message=(
                            "銘柄登録不可: "
                            f"{str(error).strip() or type(error).__name__}"
                        ),
                        attempts=self.maximum_attempts,
                    )
                )
                self.progress_reporter(
                    f"[{processed_counter[0]}/{total}] "
                    f"{code} SKIPPED registration failed"
                )
                return

            middle = max(1, len(code_batch) // 2)
            left = code_batch[:middle]
            right = code_batch[middle:]

            self.progress_reporter(
                "REGISTER BATCH SPLIT "
                f"count={len(code_batch)} "
                f"-> {len(left)} + {len(right)}"
            )

            self._collect_registered_batch(
                trading_date=trading_date,
                code_batch=left,
                bars=bars,
                failures=failures,
                skips=skips,
                processed_counter=processed_counter,
                total=total,
            )
            self._collect_registered_batch(
                trading_date=trading_date,
                code_batch=right,
                bars=bars,
                failures=failures,
                skips=skips,
                processed_counter=processed_counter,
                total=total,
            )
            return

        try:
            for code in code_batch:
                processed_counter[0] += 1
                self.progress_reporter(
                    f"[{processed_counter[0]}/{total}] "
                    f"{code} requesting..."
                )
                self._collect_one_unregistered(
                    code=code,
                    trading_date=trading_date,
                    bars=bars,
                    failures=failures,
                    skips=skips,
                )

                if (
                    processed_counter[0] < total
                    and self.request_interval_seconds > 0
                ):
                    self.sleeper(
                        self.request_interval_seconds
                    )
        finally:
            try:
                self._unregister_all_with_retry()
            except Exception as error:
                self.progress_reporter(
                    "WARNING: unregister_all failed: "
                    f"{type(error).__name__}: {error}"
                )

    def _collect_one_unregistered(
        self,
        *,
        code: str,
        trading_date: date,
        bars: list[UniverseDailyBar],
        failures: list[UniverseDailyCollectionFailure],
        skips: list[UniverseDailyCollectionSkip],
    ) -> None:
        """1銘柄をBoard APIから取得して結果へ追加する。"""

        payload = None
        last_error: Exception | None = None
        attempts = 0

        for attempt in range(
            1,
            self.maximum_attempts + 1,
        ):
            attempts = attempt
            started = time.monotonic()

            try:
                payload = self.client.board(
                    KabuStationSymbol(
                        code=code,
                        exchange=self.exchange,
                    )
                )
                elapsed = time.monotonic() - started
                self.progress_reporter(
                    f"  OK {elapsed:.2f}s "
                    f"attempt={attempt}"
                )
                break
            except Exception as error:
                last_error = error
                elapsed = time.monotonic() - started
                self.progress_reporter(
                    "  RETRY "
                    f"{elapsed:.2f}s "
                    f"attempt={attempt} "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                if attempt < self.maximum_attempts:
                    self.sleeper(
                        self.retry_backoff_seconds
                        * attempt
                    )

        if payload is None:
            error = (
                last_error
                or RuntimeError(
                    "Board API応答を取得できませんでした。"
                )
            )
            failures.append(
                UniverseDailyCollectionFailure(
                    code=code,
                    error_type=type(error).__name__,
                    message=(
                        str(error).strip()
                        or type(error).__name__
                    ),
                    attempts=attempts,
                )
            )
            return

        try:
            bar, skip_reason = self._to_daily_bar(
                code=code,
                trading_date=trading_date,
                payload=payload,
            )
            if bar is None:
                skips.append(
                    UniverseDailyCollectionSkip(
                        code=code,
                        reason=(
                            skip_reason
                            or (
                                "日足作成に必要な"
                                "値が不足しています。"
                            )
                        ),
                    )
                )
                self.progress_reporter(
                    "  SKIPPED "
                    f"{skips[-1].reason}"
                )
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
                    attempts=attempts,
                )
            )

    def _register_batch(
        self,
        symbols: tuple[KabuStationSymbol, ...],
    ) -> None:
        """登録上限内の銘柄群を再試行付きで登録する。"""

        last_error: Exception | None = None

        for attempt in range(
            1,
            self.maximum_attempts + 1,
        ):
            try:
                self.client.unregister_all()
                self.client.register_symbols(symbols)
                self.progress_reporter(
                    "  REGISTERED "
                    f"count={len(symbols)} "
                    f"attempt={attempt}"
                )
                return
            except Exception as error:
                last_error = error
                self.progress_reporter(
                    "  REGISTER RETRY "
                    f"attempt={attempt} "
                    f"{type(error).__name__}: {error}"
                )

                if attempt < self.maximum_attempts:
                    self.sleeper(
                        self.retry_backoff_seconds * attempt
                    )

        error = (
            last_error
            or RuntimeError(
                "銘柄登録に失敗しました。"
            )
        )
        raise RuntimeError(
            "候補ユニバースの銘柄登録に失敗しました。 "
            f"count={len(symbols)}"
        ) from error

    def _unregister_all_with_retry(self) -> None:
        """登録銘柄を再試行付きで全解除する。"""

        last_error: Exception | None = None

        for attempt in range(
            1,
            self.maximum_attempts + 1,
        ):
            try:
                self.client.unregister_all()
                return
            except Exception as error:
                last_error = error

                if attempt < self.maximum_attempts:
                    self.sleeper(
                        self.retry_backoff_seconds * attempt
                    )

        if last_error is not None:
            raise last_error

    @staticmethod
    def _batches(
        values: tuple[str, ...],
        size: int,
    ) -> tuple[tuple[str, ...], ...]:
        """登録上限に合わせてコードを分割する。"""

        return tuple(
            values[index:index + size]
            for index in range(0, len(values), size)
        )

    def _load_universe_codes(self) -> tuple[str, ...]:
        if not self.database_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.database_path}"
            )

        with sqlite3.connect(self.database_path) as connection:
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
            tuple(str(row[0]) for row in rows)
        )

    @staticmethod
    def _normalize_codes(
        codes: Sequence[str],
    ) -> tuple[str, ...]:
        """東証の数字・英字入り証券コードを正規化する。"""

        normalized_codes: list[str] = []

        for value in codes:
            normalized = str(value).strip().upper()

            if not normalized:
                continue

            if not re.fullmatch(
                r"[0-9A-Z]{4,5}",
                normalized,
            ):
                continue

            normalized_codes.append(normalized)

        return tuple(dict.fromkeys(normalized_codes))

    def _to_daily_bar(
        self,
        *,
        code: str,
        trading_date: date,
        payload: dict[str, object],
    ) -> tuple[UniverseDailyBar | None, str | None]:
        values = {
            "OpeningPrice": self._positive_float(
                payload.get("OpeningPrice")
            ),
            "HighPrice": self._positive_float(
                payload.get("HighPrice")
            ),
            "LowPrice": self._positive_float(
                payload.get("LowPrice")
            ),
            "CurrentPrice": self._positive_float(
                payload.get("CurrentPrice")
            ),
            "TradingVolume": self._nonnegative_int(
                payload.get("TradingVolume")
            ),
        }

        missing = [
            name
            for name, value in values.items()
            if value is None
        ]

        if missing:
            return None, (
                "Board応答の値がありません: "
                + ",".join(missing)
            )

        volume = int(values["TradingVolume"])
        if volume <= 0:
            return None, "TradingVolumeが0です。"

        open_price = float(values["OpeningPrice"])
        high_price = float(values["HighPrice"])
        low_price = float(values["LowPrice"])
        close_price = float(values["CurrentPrice"])

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

        return (
            UniverseDailyBar(
                code=code,
                trading_date=trading_date,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                data_source=self.source_name,
            ),
            None,
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
