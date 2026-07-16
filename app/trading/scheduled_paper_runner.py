"""Paper Tradingパイプラインを定刻・一日一回だけ実行する。"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

from app.market.models import StockPrice
from app.trading.order_models import OrderType
from app.trading.paper_trading_pipeline import (
    PaperTradingPipelineResult,
)


JAPAN_TIMEZONE = ZoneInfo(
    "Asia/Tokyo",
)


class ScheduledPriceLoader(Protocol):
    """定刻運用で利用する価格データ取得処理。"""

    def load(
        self,
        *,
        trading_date: date,
    ) -> list[StockPrice]:
        """指定営業日の価格データを返す。"""


class ScheduledPaperPipeline(Protocol):
    """定刻運用で利用するPaper Tradingパイプライン。"""

    def run(
        self,
        prices: list[StockPrice],
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        report_generated_at: datetime | None = None,
        report_csv_path: object | None = None,
        continue_on_error: bool = True,
    ) -> PaperTradingPipelineResult:
        """価格データからPaper Tradingを実行する。"""


class ScheduledRunStateStore(Protocol):
    """定刻実行済み日付を管理する保存処理。"""

    def has_completed(
        self,
        *,
        trading_date: date,
        process_name: str,
    ) -> bool:
        """指定日・処理名が完了済みか返す。"""

    def mark_completed(
        self,
        *,
        trading_date: date,
        process_name: str,
        completed_at: datetime,
    ) -> None:
        """指定日・処理名を完了済みとして保存する。"""


class ScheduledPaperRunDecision(StrEnum):
    """定刻Paper Tradingランナーの実行結果。"""

    EXECUTED = "executed"
    SKIPPED_BEFORE_TIME = "skipped_before_time"
    SKIPPED_NON_TRADING_DAY = "skipped_non_trading_day"
    SKIPPED_ALREADY_COMPLETED = "skipped_already_completed"
    SKIPPED_NO_PRICES = "skipped_no_prices"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ScheduledPaperRunnerSettings:
    """定刻Paper Tradingの実行条件。"""

    process_name: str = "paper-trading"
    execution_time: time = time(
        9,
        25,
    )
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None

    def __post_init__(self) -> None:
        """設定値を検証する。"""

        normalized_process_name = (
            self.process_name.strip()
        )

        if not normalized_process_name:
            raise ValueError(
                "処理名を指定してください。"
            )

        if (
            self.order_type is OrderType.MARKET
            and (
                self.limit_price is not None
                or self.stop_price is not None
            )
        ):
            raise ValueError(
                "成行注文には指値価格・逆指値価格を"
                "設定できません。"
            )

        if (
            self.order_type is OrderType.LIMIT
            and self.limit_price is None
        ):
            raise ValueError(
                "指値注文には指値価格が必要です。"
            )

        if (
            self.order_type is OrderType.STOP
            and self.stop_price is None
        ):
            raise ValueError(
                "逆指値注文には逆指値価格が必要です。"
            )

        if (
            self.order_type is OrderType.STOP_LIMIT
            and (
                self.limit_price is None
                or self.stop_price is None
            )
        ):
            raise ValueError(
                "逆指値付き指値注文には"
                "指値価格と逆指値価格が必要です。"
            )

        object.__setattr__(
            self,
            "process_name",
            normalized_process_name,
        )


@dataclass(frozen=True, slots=True)
class ScheduledPaperRunResult:
    """定刻Paper Tradingの1回分の結果。"""

    decision: ScheduledPaperRunDecision
    trading_date: date
    checked_at: datetime
    price_count: int
    pipeline_result: PaperTradingPipelineResult | None
    message: str | None

    @property
    def was_executed(self) -> bool:
        """パイプラインを実行したか返す。"""

        return (
            self.decision
            is ScheduledPaperRunDecision.EXECUTED
        )

    @property
    def was_skipped(self) -> bool:
        """正常な条件判定でスキップしたか返す。"""

        return self.decision in {
            ScheduledPaperRunDecision.SKIPPED_BEFORE_TIME,
            ScheduledPaperRunDecision.SKIPPED_NON_TRADING_DAY,
            ScheduledPaperRunDecision.SKIPPED_ALREADY_COMPLETED,
            ScheduledPaperRunDecision.SKIPPED_NO_PRICES,
        }

    @property
    def is_failed(self) -> bool:
        """処理が失敗したか返す。"""

        return (
            self.decision
            is ScheduledPaperRunDecision.FAILED
        )


class InMemoryScheduledRunStateStore:
    """テスト・単一プロセス運用向けの実行済み状態保存。"""

    def __init__(
        self,
    ) -> None:
        """空の完了状態を作成する。"""

        self._completed: set[
            tuple[
                date,
                str,
            ]
        ] = set()

    def has_completed(
        self,
        *,
        trading_date: date,
        process_name: str,
    ) -> bool:
        """指定日・処理名が完了済みか返す。"""

        return (
            trading_date,
            process_name,
        ) in self._completed

    def mark_completed(
        self,
        *,
        trading_date: date,
        process_name: str,
        completed_at: datetime,
    ) -> None:
        """指定日・処理名を完了済みとして保存する。"""

        if completed_at.tzinfo is None:
            raise ValueError(
                "完了日時にはタイムゾーンが必要です。"
            )

        self._completed.add(
            (
                trading_date,
                process_name,
            )
        )


class ScheduledPaperTradingRunner:
    """取引日・時刻・重複を確認してPaper Tradingを実行する。"""

    def __init__(
        self,
        *,
        price_loader: ScheduledPriceLoader,
        pipeline: ScheduledPaperPipeline,
        state_store: ScheduledRunStateStore,
        settings: ScheduledPaperRunnerSettings | None = None,
    ) -> None:
        """必要なサービスと設定を受け取る。"""

        self.price_loader = price_loader
        self.pipeline = pipeline
        self.state_store = state_store
        self.settings = (
            settings
            if settings is not None
            else ScheduledPaperRunnerSettings()
        )

    def run_once(
        self,
        *,
        now: datetime | None = None,
        continue_on_error: bool = True,
    ) -> ScheduledPaperRunResult:
        """現在日時を基準に1回だけ運用判定・実行する。"""

        checked_at = self._resolve_now(
            now,
        )
        japan_time = checked_at.astimezone(
            JAPAN_TIMEZONE,
        )
        trading_date = japan_time.date()

        try:
            if japan_time.weekday() >= 5:
                return ScheduledPaperRunResult(
                    decision=(
                        ScheduledPaperRunDecision
                        .SKIPPED_NON_TRADING_DAY
                    ),
                    trading_date=trading_date,
                    checked_at=checked_at,
                    price_count=0,
                    pipeline_result=None,
                    message=(
                        "土曜日または日曜日のため"
                        "実行しませんでした。"
                    ),
                )

            if japan_time.time() < self.settings.execution_time:
                return ScheduledPaperRunResult(
                    decision=(
                        ScheduledPaperRunDecision
                        .SKIPPED_BEFORE_TIME
                    ),
                    trading_date=trading_date,
                    checked_at=checked_at,
                    price_count=0,
                    pipeline_result=None,
                    message=(
                        "指定実行時刻より前のため"
                        "実行しませんでした。"
                    ),
                )

            if self.state_store.has_completed(
                trading_date=trading_date,
                process_name=self.settings.process_name,
            ):
                return ScheduledPaperRunResult(
                    decision=(
                        ScheduledPaperRunDecision
                        .SKIPPED_ALREADY_COMPLETED
                    ),
                    trading_date=trading_date,
                    checked_at=checked_at,
                    price_count=0,
                    pipeline_result=None,
                    message=(
                        "当日の処理は既に完了しています。"
                    ),
                )

            prices = self.price_loader.load(
                trading_date=trading_date,
            )

            if not prices:
                return ScheduledPaperRunResult(
                    decision=(
                        ScheduledPaperRunDecision
                        .SKIPPED_NO_PRICES
                    ),
                    trading_date=trading_date,
                    checked_at=checked_at,
                    price_count=0,
                    pipeline_result=None,
                    message=(
                        "対象日の価格データがありません。"
                    ),
                )

            pipeline_result = self.pipeline.run(
                prices,
                order_type=self.settings.order_type,
                limit_price=self.settings.limit_price,
                stop_price=self.settings.stop_price,
                report_generated_at=checked_at,
                continue_on_error=continue_on_error,
            )

            if not pipeline_result.is_successful:
                raise RuntimeError(
                    "Paper Tradingパイプラインが"
                    "失敗結果を返しました。"
                )

            self.state_store.mark_completed(
                trading_date=trading_date,
                process_name=self.settings.process_name,
                completed_at=checked_at,
            )

            return ScheduledPaperRunResult(
                decision=(
                    ScheduledPaperRunDecision.EXECUTED
                ),
                trading_date=trading_date,
                checked_at=checked_at,
                price_count=len(prices),
                pipeline_result=pipeline_result,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return ScheduledPaperRunResult(
                decision=(
                    ScheduledPaperRunDecision.FAILED
                ),
                trading_date=trading_date,
                checked_at=checked_at,
                price_count=0,
                pipeline_result=None,
                message=str(error),
            )

    @staticmethod
    def _resolve_now(
        now: datetime | None,
    ) -> datetime:
        """タイムゾーン付きUTC日時を返す。"""

        resolved_now = (
            now
            if now is not None
            else datetime.now(timezone.utc)
        )

        if resolved_now.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return resolved_now.astimezone(
            timezone.utc,
        )