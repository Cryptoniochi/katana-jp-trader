"""kabuステーションBoard APIから候補ユニバースの日足を収集する。"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        return {"code": self.code, "reason": self.reason}


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
            "meets_minimum_success_ratio": self.meets_minimum_success_ratio,
            "completed": self.completed,
            "source_name": self.source_name,
            "skips": [item.to_dict() for item in self.skips],
            "failures": [failure.to_dict() for failure in self.failures],
        }


@dataclass(slots=True)
class BoardRequestMetrics:
    """1回のCollector実行中のBoard API応答統計。"""

    request_count: int = 0
    first_attempt_success_count: int = 0
    retry_success_count: int = 0
    failed_symbol_count: int = 0
    timeout_like_count: int = 0
    total_elapsed_seconds: float = 0.0
    first_attempt_elapsed_seconds: float = 0.0
    retry_elapsed_seconds: float = 0.0
    first_attempt_count: int = 0
    retry_attempt_count: int = 0

    @property
    def first_attempt_success_ratio(self) -> float:
        if self.first_attempt_count <= 0:
            return 0.0
        return self.first_attempt_success_count / self.first_attempt_count

    @property
    def average_first_attempt_seconds(self) -> float:
        if self.first_attempt_count <= 0:
            return 0.0
        return self.first_attempt_elapsed_seconds / self.first_attempt_count

    @property
    def average_retry_seconds(self) -> float:
        if self.retry_attempt_count <= 0:
            return 0.0
        return self.retry_elapsed_seconds / self.retry_attempt_count

    def to_dict(self) -> dict[str, object]:
        return {
            "request_count": self.request_count,
            "first_attempt_count": self.first_attempt_count,
            "first_attempt_success_count": self.first_attempt_success_count,
            "first_attempt_success_ratio": round(
                self.first_attempt_success_ratio, 6
            ),
            "retry_attempt_count": self.retry_attempt_count,
            "retry_success_count": self.retry_success_count,
            "timeout_like_count": self.timeout_like_count,
            "failed_symbol_count": self.failed_symbol_count,
            "average_first_attempt_seconds": round(
                self.average_first_attempt_seconds, 6
            ),
            "average_retry_seconds": round(
                self.average_retry_seconds, 6
            ),
            "total_elapsed_seconds": round(
                self.total_elapsed_seconds, 6
            ),
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
        metrics_report_path: Path | None = None,
        board_first_attempt_timeout_seconds: float = 0.75,
        parallel_workers: int = 1,
    ) -> None:
        if request_interval_seconds < 0:
            raise ValueError("API呼出し間隔は0以上である必要があります。")
        if not 0 < minimum_success_ratio <= 1:
            raise ValueError("最低成功率は0より大きく1以下である必要があります。")
        if maximum_attempts <= 0:
            raise ValueError("最大試行回数は1以上である必要があります。")
        if retry_backoff_seconds < 0:
            raise ValueError("再試行待機秒数は0以上である必要があります。")
        if board_first_attempt_timeout_seconds <= 0:
            raise ValueError(
                "Board初回タイムアウト秒数は0より大きい必要があります。"
            )
        if parallel_workers <= 0:
            raise ValueError("Board並列ワーカー数は1以上である必要があります。")

        self.client = client
        settings = getattr(client, "settings", None)
        maximum_registered = int(
            getattr(settings, "maximum_registered_symbols", 50)
        )
        resolved_batch_size = (
            maximum_registered
            if registration_batch_size is None
            else int(registration_batch_size)
        )
        if resolved_batch_size <= 0:
            raise ValueError("登録バッチサイズは1以上である必要があります。")
        if resolved_batch_size > maximum_registered:
            raise ValueError(
                "登録バッチサイズがkabuステーションの登録上限を超えています。 "
                f"batch_size={resolved_batch_size} maximum={maximum_registered}"
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
            callable(getattr(self.client, "register_symbols", None))
            and callable(getattr(self.client, "unregister_all", None))
        )
        self.sleeper = sleeper
        self.progress_reporter = (
            progress_reporter if progress_reporter is not None
            else lambda _message: None
        )
        self.now_provider = (
            now_provider if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.metrics_report_path = (
            None if metrics_report_path is None else Path(metrics_report_path)
        )
        self.board_first_attempt_timeout_seconds = float(
            board_first_attempt_timeout_seconds
        )
        self.parallel_workers = int(parallel_workers)
        self.board_metrics = BoardRequestMetrics()
        self.board_readiness_trace: list[dict[str, object]] = []
        self._metrics_lock = threading.Lock()
        self._collection_wall_started: float | None = None
        self._collection_wall_elapsed_seconds = 0.0

    def collect(
        self,
        *,
        trading_date: date,
        codes: Sequence[str] | None = None,
    ) -> UniverseDailyCollectionResult:
        """指定日の候補ユニバース日足を収集・保存する。"""

        self.board_metrics = BoardRequestMetrics()
        self.board_readiness_trace = []
        self._collection_wall_started = time.monotonic()
        self._collection_wall_elapsed_seconds = 0.0
        resolved_codes = (
            self._load_universe_codes()
            if codes is None
            else self._normalize_codes(codes)
        )
        if not resolved_codes:
            raise RuntimeError("日足収集対象の候補ユニバースが空です。")

        self.client.issue_token()
        bars: list[UniverseDailyBar] = []
        failures: list[UniverseDailyCollectionFailure] = []
        skips: list[UniverseDailyCollectionSkip] = []
        saved_count = 0
        total = len(resolved_codes)
        processed_counter = [0]
        saved_counter = [0]

        try:
            if self._registration_supported:
                for batch_number, code_batch in enumerate(
                    self._batches(resolved_codes, self.registration_batch_size),
                    start=1,
                ):
                    self.progress_reporter(
                        f"Registering batch {batch_number}: count={len(code_batch)}"
                    )
                    self._collect_registered_batch(
                        trading_date=trading_date,
                        code_batch=code_batch,
                        bars=bars,
                        failures=failures,
                        skips=skips,
                        processed_counter=processed_counter,
                        saved_counter=saved_counter,
                        total=total,
                    )
                saved_count = saved_counter[0]
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
                        self.sleeper(self.request_interval_seconds)
                saved_count = self.repository.upsert_many(tuple(bars))
        finally:
            if self._collection_wall_started is not None:
                self._collection_wall_elapsed_seconds = (
                    time.monotonic() - self._collection_wall_started
                )
            if self._registration_supported:
                try:
                    self._unregister_all_with_retry()
                except Exception as error:
                    self.progress_reporter(
                        "WARNING: unregister_all failed: "
                        f"{type(error).__name__}: {error}"
                    )
            self._report_board_metrics()
            self._persist_board_metrics(
                trading_date=trading_date,
                requested_count=total,
                collected_count=len(bars),
                saved_count=saved_count if saved_count else saved_counter[0],
                failure_count=len(failures),
                skipped_count=len(skips),
            )

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
                "候補ユニバース日足の収集成功率が基準を下回りました。 "
                f"requested={result.requested_count} "
                f"collected={result.collected_count} "
                f"ratio={result.success_ratio:.3f} "
                f"minimum={result.minimum_success_ratio:.3f}"
            )
        return result

    def _collect_registered_batch(
        self, *, trading_date: date, code_batch: tuple[str, ...],
        bars: list[UniverseDailyBar],
        failures: list[UniverseDailyCollectionFailure],
        skips: list[UniverseDailyCollectionSkip],
        processed_counter: list[int], saved_counter: list[int], total: int,
    ) -> None:
        if not code_batch:
            return
        symbols = tuple(
            KabuStationSymbol(code=code, exchange=self.exchange)
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
                        code=code, error_type=type(error).__name__,
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
            left, right = code_batch[:middle], code_batch[middle:]
            self.progress_reporter(
                f"REGISTER BATCH SPLIT count={len(code_batch)} "
                f"-> {len(left)} + {len(right)}"
            )
            for part in (left, right):
                self._collect_registered_batch(
                    trading_date=trading_date, code_batch=part, bars=bars,
                    failures=failures, skips=skips,
                    processed_counter=processed_counter,
                    saved_counter=saved_counter, total=total,
                )
            return

        registered_at = time.monotonic()

        try:
            if self.parallel_workers <= 1 or len(code_batch) <= 1:
                self._collect_registered_batch_sequential(
                    trading_date=trading_date,
                    code_batch=code_batch,
                    bars=bars,
                    failures=failures,
                    skips=skips,
                    processed_counter=processed_counter,
                    saved_counter=saved_counter,
                    total=total,
                    registered_at=registered_at,
                )
            else:
                self._collect_registered_batch_parallel(
                    trading_date=trading_date,
                    code_batch=code_batch,
                    bars=bars,
                    failures=failures,
                    skips=skips,
                    processed_counter=processed_counter,
                    saved_counter=saved_counter,
                    total=total,
                    registered_at=registered_at,
                )
        finally:
            try:
                self._unregister_all_with_retry()
            except Exception as error:
                self.progress_reporter(
                    "WARNING: unregister_all failed: "
                    f"{type(error).__name__}: {error}"
                )

    def _collect_registered_batch_sequential(
        self,
        *,
        trading_date: date,
        code_batch: tuple[str, ...],
        bars: list[UniverseDailyBar],
        failures: list[UniverseDailyCollectionFailure],
        skips: list[UniverseDailyCollectionSkip],
        processed_counter: list[int],
        saved_counter: list[int],
        total: int,
        registered_at: float,
    ) -> None:
        for code in code_batch:
            processed_counter[0] += 1
            self.progress_reporter(
                f"[{processed_counter[0]}/{total}] {code} requesting..."
            )
            before_count = len(bars)
            self._collect_one_unregistered(
                code=code,
                trading_date=trading_date,
                bars=bars,
                failures=failures,
                skips=skips,
                registered_at=registered_at,
            )
            if len(bars) > before_count:
                bar = bars[-1]
                saved = self.repository.upsert_many((bar,))
                saved_counter[0] += saved
                self.progress_reporter(
                    f"  PERSISTED code={code} saved={saved} "
                    f"saved_total={saved_counter[0]}"
                )
            if (
                processed_counter[0] < total
                and self.request_interval_seconds > 0
            ):
                self.sleeper(self.request_interval_seconds)

    def _collect_registered_batch_parallel(
        self,
        *,
        trading_date: date,
        code_batch: tuple[str, ...],
        bars: list[UniverseDailyBar],
        failures: list[UniverseDailyCollectionFailure],
        skips: list[UniverseDailyCollectionSkip],
        processed_counter: list[int],
        saved_counter: list[int],
        total: int,
        registered_at: float,
    ) -> None:
        """Board取得だけを並列化し、SQLite保存はメインスレッドで直列化する。"""

        worker_count = min(self.parallel_workers, len(code_batch))
        self.progress_reporter(
            f"BOARD PARALLEL workers={worker_count} count={len(code_batch)}"
        )

        def worker(code: str):
            local_bars: list[UniverseDailyBar] = []
            local_failures: list[UniverseDailyCollectionFailure] = []
            local_skips: list[UniverseDailyCollectionSkip] = []
            self._collect_one_unregistered(
                code=code,
                trading_date=trading_date,
                bars=local_bars,
                failures=local_failures,
                skips=local_skips,
                registered_at=registered_at,
            )
            return code, local_bars, local_failures, local_skips

        futures = {}
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for index, code in enumerate(code_batch):
                futures[executor.submit(worker, code)] = code
                if (
                    index < len(code_batch) - 1
                    and self.request_interval_seconds > 0
                ):
                    self.sleeper(self.request_interval_seconds)

            for future in as_completed(futures):
                code = futures[future]
                processed_counter[0] += 1
                self.progress_reporter(
                    f"[{processed_counter[0]}/{total}] {code} completed"
                )
                try:
                    (
                        _,
                        local_bars,
                        local_failures,
                        local_skips,
                    ) = future.result()
                except Exception as error:
                    local_bars = []
                    local_skips = []
                    local_failures = [
                        UniverseDailyCollectionFailure(
                            code=code,
                            error_type=type(error).__name__,
                            message=str(error).strip()
                            or type(error).__name__,
                            attempts=self.maximum_attempts,
                        )
                    ]

                failures.extend(local_failures)
                skips.extend(local_skips)

                for bar in local_bars:
                    bars.append(bar)
                    saved = self.repository.upsert_many((bar,))
                    saved_counter[0] += saved
                    self.progress_reporter(
                        f"  PERSISTED code={code} saved={saved} "
                        f"saved_total={saved_counter[0]}"
                    )

    def _collect_one_unregistered(
        self, *, code: str, trading_date: date,
        bars: list[UniverseDailyBar],
        failures: list[UniverseDailyCollectionFailure],
        skips: list[UniverseDailyCollectionSkip],
        registered_at: float | None = None,
    ) -> None:
        payload = None
        last_error: Exception | None = None
        attempts = 0

        for attempt in range(1, self.maximum_attempts + 1):
            attempts = attempt
            started = time.monotonic()
            with self._metrics_lock:
                self.board_metrics.request_count += 1
                if attempt == 1:
                    self.board_metrics.first_attempt_count += 1
                else:
                    self.board_metrics.retry_attempt_count += 1

            try:
                symbol = KabuStationSymbol(
                    code=code,
                    exchange=self.exchange,
                )
                if attempt == 1:
                    payload = self._board_first_attempt(symbol)
                else:
                    payload = self.client.board(symbol)
                elapsed = time.monotonic() - started
                self._record_elapsed(attempt, elapsed)
                self._record_readiness_trace(
                    code=code,
                    attempt=attempt,
                    started=started,
                    registered_at=registered_at,
                    elapsed=elapsed,
                    success=True,
                    timeout_like=False,
                )
                with self._metrics_lock:
                    if attempt == 1:
                        self.board_metrics.first_attempt_success_count += 1
                    else:
                        self.board_metrics.retry_success_count += 1
                self.progress_reporter(
                    f"  OK {elapsed:.2f}s attempt={attempt}"
                )
                break
            except Exception as error:
                last_error = error
                elapsed = time.monotonic() - started
                self._record_elapsed(attempt, elapsed)
                timeout_like = self._is_timeout_like(error)
                self._record_readiness_trace(
                    code=code,
                    attempt=attempt,
                    started=started,
                    registered_at=registered_at,
                    elapsed=elapsed,
                    success=False,
                    timeout_like=timeout_like,
                )
                if timeout_like:
                    with self._metrics_lock:
                        self.board_metrics.timeout_like_count += 1
                self.progress_reporter(
                    f"  RETRY {elapsed:.2f}s attempt={attempt} "
                    f"{type(error).__name__}: {error}"
                )
                if (
                    attempt < self.maximum_attempts
                    and self.retry_backoff_seconds > 0
                ):
                    self.sleeper(self.retry_backoff_seconds * attempt)

        if payload is None:
            with self._metrics_lock:
                self.board_metrics.failed_symbol_count += 1
            error = last_error or RuntimeError(
                "Board API応答を取得できませんでした。"
            )
            failures.append(
                UniverseDailyCollectionFailure(
                    code=code, error_type=type(error).__name__,
                    message=str(error).strip() or type(error).__name__,
                    attempts=attempts,
                )
            )
            return

        try:
            bar, skip_reason = self._to_daily_bar(
                code=code, trading_date=trading_date, payload=payload
            )
            if bar is None:
                skips.append(
                    UniverseDailyCollectionSkip(
                        code=code,
                        reason=skip_reason or "日足作成に必要な値が不足しています。",
                    )
                )
                self.progress_reporter(f"  SKIPPED {skips[-1].reason}")
            else:
                bars.append(bar)
        except Exception as error:
            failures.append(
                UniverseDailyCollectionFailure(
                    code=code, error_type=type(error).__name__,
                    message=str(error).strip() or type(error).__name__,
                    attempts=attempts,
                )
            )

    def _board_first_attempt(
        self,
        symbol: KabuStationSymbol,
    ) -> dict[str, object]:
        """Board初回だけ短いtimeoutを使う。

        旧FakeClientなどtimeout_seconds引数を持たないClientは、
        既存テスト互換のため従来board呼出しへフォールバックする。
        """

        board_method = self.client.board
        try:
            return board_method(
                symbol,
                timeout_seconds=self.board_first_attempt_timeout_seconds,
            )
        except TypeError as error:
            message = str(error)
            if (
                "timeout_seconds" not in message
                and "unexpected keyword" not in message
            ):
                raise
            return board_method(symbol)

    def _record_readiness_trace(
        self,
        *,
        code: str,
        attempt: int,
        started: float,
        registered_at: float | None,
        elapsed: float,
        success: bool,
        timeout_like: bool,
    ) -> None:
        """Board要求開始時点の登録後経過時間と成否を記録する。"""

        if registered_at is None:
            seconds_since_registration = None
        else:
            seconds_since_registration = max(
                0.0,
                started - registered_at,
            )

        timeout_seconds = (
            self.board_first_attempt_timeout_seconds
            if attempt == 1
            else float(
                getattr(
                    getattr(self.client, "settings", None),
                    "timeout_seconds",
                    0.0,
                )
            )
        )

        with self._metrics_lock:
            self.board_readiness_trace.append(
                {
                "code": code,
                "attempt": attempt,
                "seconds_since_registration": (
                    None
                    if seconds_since_registration is None
                    else round(seconds_since_registration, 6)
                ),
                "timeout_seconds": round(timeout_seconds, 6),
                "elapsed_seconds": round(elapsed, 6),
                "success": success,
                    "timeout_like": timeout_like,
                }
            )

    def _build_first_attempt_readiness_profile(
        self,
    ) -> list[dict[str, object]]:
        """初回Board成否を登録後経過時間帯ごとに集計する。"""

        bucket_definitions = (
            ("0-5s", 0.0, 5.0),
            ("5-15s", 5.0, 15.0),
            ("15-30s", 15.0, 30.0),
            ("30-60s", 30.0, 60.0),
            ("60-120s", 60.0, 120.0),
            ("120s+", 120.0, None),
        )
        rows: list[dict[str, object]] = []

        first_attempts = [
            item
            for item in self.board_readiness_trace
            if item["attempt"] == 1
            and item["seconds_since_registration"] is not None
        ]

        for label, lower, upper in bucket_definitions:
            items = []
            for item in first_attempts:
                value = float(item["seconds_since_registration"])
                if value < lower:
                    continue
                if upper is not None and value >= upper:
                    continue
                items.append(item)

            if not items:
                continue

            success_count = sum(
                1 for item in items if bool(item["success"])
            )
            timeout_count = sum(
                1 for item in items if bool(item["timeout_like"])
            )
            rows.append(
                {
                    "window": label,
                    "attempt_count": len(items),
                    "success_count": success_count,
                    "success_ratio": round(
                        success_count / len(items),
                        6,
                    ),
                    "timeout_like_count": timeout_count,
                    "average_elapsed_seconds": round(
                        sum(
                            float(item["elapsed_seconds"])
                            for item in items
                        )
                        / len(items),
                        6,
                    ),
                }
            )

        return rows

    def _build_attempt_profile(self) -> list[dict[str, object]]:
        """Board APIの試行回数ごとに成功率・timeout率・応答時間を集計する。"""

        rows: list[dict[str, object]] = []
        if not self.board_readiness_trace:
            return rows

        maximum_attempt = max(
            int(item["attempt"])
            for item in self.board_readiness_trace
        )

        for attempt in range(1, maximum_attempt + 1):
            items = [
                item
                for item in self.board_readiness_trace
                if int(item["attempt"]) == attempt
            ]
            if not items:
                continue

            success_count = sum(
                1 for item in items if bool(item["success"])
            )
            timeout_count = sum(
                1 for item in items if bool(item["timeout_like"])
            )
            elapsed_values = [
                float(item["elapsed_seconds"])
                for item in items
            ]
            successful_elapsed_values = [
                float(item["elapsed_seconds"])
                for item in items
                if bool(item["success"])
            ]
            failed_elapsed_values = [
                float(item["elapsed_seconds"])
                for item in items
                if not bool(item["success"])
            ]

            timeout_seconds_values = {
                float(item["timeout_seconds"])
                for item in items
            }
            timeout_seconds = (
                next(iter(timeout_seconds_values))
                if len(timeout_seconds_values) == 1
                else None
            )

            rows.append(
                {
                    "attempt": attempt,
                    "attempt_count": len(items),
                    "success_count": success_count,
                    "success_ratio": round(
                        success_count / len(items),
                        6,
                    ),
                    "timeout_like_count": timeout_count,
                    "timeout_like_ratio": round(
                        timeout_count / len(items),
                        6,
                    ),
                    "configured_timeout_seconds": (
                        None
                        if timeout_seconds is None
                        else round(timeout_seconds, 6)
                    ),
                    "average_elapsed_seconds": round(
                        sum(elapsed_values) / len(elapsed_values),
                        6,
                    ),
                    "average_success_elapsed_seconds": (
                        None
                        if not successful_elapsed_values
                        else round(
                            sum(successful_elapsed_values)
                            / len(successful_elapsed_values),
                            6,
                        )
                    ),
                    "average_failed_elapsed_seconds": (
                        None
                        if not failed_elapsed_values
                        else round(
                            sum(failed_elapsed_values)
                            / len(failed_elapsed_values),
                            6,
                        )
                    ),
                }
            )

        return rows

    def _record_elapsed(self, attempt: int, elapsed: float) -> None:
        with self._metrics_lock:
            self.board_metrics.total_elapsed_seconds += elapsed
            if attempt == 1:
                self.board_metrics.first_attempt_elapsed_seconds += elapsed
            else:
                self.board_metrics.retry_elapsed_seconds += elapsed

    @staticmethod
    def _is_timeout_like(error: Exception) -> bool:
        text = f"{type(error).__name__} {error}".lower()
        return "timeout" in text or "timed out" in text

    def _report_board_metrics(self) -> None:
        metrics = self.board_metrics
        self.progress_reporter(
            "BOARD METRICS "
            f"requests={metrics.request_count} "
            f"first_attempts={metrics.first_attempt_count} "
            f"first_success={metrics.first_attempt_success_count} "
            f"first_success_ratio={metrics.first_attempt_success_ratio:.3f} "
            f"retry_attempts={metrics.retry_attempt_count} "
            f"retry_success={metrics.retry_success_count} "
            f"timeouts={metrics.timeout_like_count} "
            f"failed_symbols={metrics.failed_symbol_count} "
            f"avg_first={metrics.average_first_attempt_seconds:.3f}s "
            f"avg_retry={metrics.average_retry_seconds:.3f}s "
            f"board_elapsed={metrics.total_elapsed_seconds:.3f}s"
        )

    def _persist_board_metrics(
        self,
        *,
        trading_date: date,
        requested_count: int,
        collected_count: int,
        saved_count: int,
        failure_count: int,
        skipped_count: int,
    ) -> None:
        if self.metrics_report_path is None:
            return

        generated_at = self._current_time()
        payload = {
            "generated_at": generated_at.isoformat(),
            "trading_date": trading_date.isoformat(),
            "requested_count": requested_count,
            "collected_count": collected_count,
            "saved_count": saved_count,
            "failure_count": failure_count,
            "skipped_count": skipped_count,
            "source_name": self.source_name,
            "board_first_attempt_timeout_seconds": (
                self.board_first_attempt_timeout_seconds
            ),
            "parallel_workers": self.parallel_workers,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "request_interval_seconds": self.request_interval_seconds,
            "estimated_retry_backoff_budget_seconds": round(
                self.retry_backoff_seconds
                * sum(
                    max(0, int(item["attempt"]) - 1)
                    for item in self.board_readiness_trace
                    if int(item["attempt"]) > 1
                ),
                6,
            ),
            "estimated_request_interval_budget_seconds": round(
                self.request_interval_seconds
                * max(0, requested_count - 1),
                6,
            ),
            "collection_wall_elapsed_seconds": round(
                self._collection_wall_elapsed_seconds,
                6,
            ),
            "retry_timeout_seconds": float(
                getattr(
                    getattr(self.client, "settings", None),
                    "timeout_seconds",
                    0.0,
                )
            ),
            "metrics": self.board_metrics.to_dict(),
            "first_attempt_readiness_profile": (
                self._build_first_attempt_readiness_profile()
            ),
            "attempt_profile": self._build_attempt_profile(),
            "board_readiness_trace": self.board_readiness_trace,
        }

        path = self.metrics_report_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def _register_batch(
        self, symbols: tuple[KabuStationSymbol, ...]
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.maximum_attempts + 1):
            try:
                self.client.unregister_all()
                self.client.register_symbols(symbols)
                self.progress_reporter(
                    f"  REGISTERED count={len(symbols)} attempt={attempt}"
                )
                return
            except Exception as error:
                last_error = error
                self.progress_reporter(
                    f"  REGISTER RETRY attempt={attempt} "
                    f"{type(error).__name__}: {error}"
                )
                if (
                    attempt < self.maximum_attempts
                    and self.retry_backoff_seconds > 0
                ):
                    self.sleeper(self.retry_backoff_seconds * attempt)
        error = last_error or RuntimeError("銘柄登録に失敗しました。")
        raise RuntimeError(
            f"候補ユニバースの銘柄登録に失敗しました。 count={len(symbols)}"
        ) from error

    def _unregister_all_with_retry(self) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.maximum_attempts + 1):
            try:
                self.client.unregister_all()
                return
            except Exception as error:
                last_error = error
                if (
                    attempt < self.maximum_attempts
                    and self.retry_backoff_seconds > 0
                ):
                    self.sleeper(self.retry_backoff_seconds * attempt)
        if last_error is not None:
            raise last_error

    @staticmethod
    def _batches(values: tuple[str, ...], size: int) -> tuple[tuple[str, ...], ...]:
        return tuple(
            values[index:index + size] for index in range(0, len(values), size)
        )

    def _load_universe_codes(self) -> tuple[str, ...]:
        if not self.database_path.exists():
            raise FileNotFoundError(f"Database not found: {self.database_path}")
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
        return self._normalize_codes(tuple(str(row[0]) for row in rows))

    @staticmethod
    def _normalize_codes(codes: Sequence[str]) -> tuple[str, ...]:
        normalized_codes: list[str] = []
        for value in codes:
            normalized = str(value).strip().upper()
            if not normalized:
                continue
            if not re.fullmatch(r"[0-9A-Z]{4,5}", normalized):
                continue
            normalized_codes.append(normalized)
        return tuple(dict.fromkeys(normalized_codes))

    def _to_daily_bar(
        self, *, code: str, trading_date: date, payload: dict[str, object],
    ) -> tuple[UniverseDailyBar | None, str | None]:
        values = {
            "OpeningPrice": self._positive_float(payload.get("OpeningPrice")),
            "HighPrice": self._positive_float(payload.get("HighPrice")),
            "LowPrice": self._positive_float(payload.get("LowPrice")),
            "CurrentPrice": self._positive_float(payload.get("CurrentPrice")),
            "TradingVolume": self._nonnegative_int(payload.get("TradingVolume")),
        }
        missing = [name for name, value in values.items() if value is None]
        if missing:
            return None, "Board応答の値がありません: " + ",".join(missing)
        volume = int(values["TradingVolume"])
        if volume <= 0:
            return None, "TradingVolumeが0です。"
        open_price = float(values["OpeningPrice"])
        high_price = float(values["HighPrice"])
        low_price = float(values["LowPrice"])
        close_price = float(values["CurrentPrice"])
        if not (
            low_price <= min(open_price, close_price)
            <= max(open_price, close_price) <= high_price
        ):
            raise ValueError(f"Board APIのOHLC関係が不正です。 code={code}")
        return (
            UniverseDailyBar(
                code=code, trading_date=trading_date,
                open_price=open_price, high_price=high_price,
                low_price=low_price, close_price=close_price,
                volume=volume, data_source=self.source_name,
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
            raise ValueError("現在日時にはタイムゾーンが必要です。")
        return value.astimezone(timezone.utc)
