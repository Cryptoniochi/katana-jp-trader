"""リアルタイム市場データ監視の基盤サービス。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.market.models import StockPrice
from app.market.realtime_models import (
    MarketSessionSnapshot,
    MarketSessionState,
    RealtimeMarketPollResult,
    RealtimePollDecision,
)


JST = ZoneInfo("Asia/Tokyo")


class RealtimeBarProvider(Protocol):
    """当日分の時間足を取得するProvider。"""

    def __call__(
        self,
        code: str,
        target_date: date,
    ) -> list[StockPrice]:
        """指定銘柄・日付の時間足を返す。"""


class RealtimeBarRepository(Protocol):
    """リアルタイム監視で使用するRepository。"""

    def latest_datetime(
        self,
        code: str,
        interval_minutes: int,
    ) -> datetime | None:
        """保存済み最新時間足の開始日時を返す。"""

    def save_all(
        self,
        prices: list[StockPrice],
        interval_minutes: int,
        data_source: str,
    ) -> int:
        """時間足を一括保存する。"""


TradingDayPredicate = Callable[[date], bool]


class TokyoMarketSessionService:
    """東京市場の取引日と場中時間を判定する。"""

    def __init__(
        self,
        *,
        trading_day_predicate: TradingDayPredicate | None = None,
    ) -> None:
        """取引日判定処理を設定する。"""

        self.trading_day_predicate = (
            trading_day_predicate
            if trading_day_predicate is not None
            else self._is_weekday
        )

    def create_snapshot(
        self,
        observed_at: datetime,
    ) -> MarketSessionSnapshot:
        """指定日時の市場状態を返す。"""

        if observed_at.tzinfo is None:
            raise ValueError(
                "監視日時にはタイムゾーンが必要です。"
            )

        local_time = observed_at.astimezone(JST)
        trading_date = local_time.date()
        is_trading_day = self.trading_day_predicate(
            trading_date
        )

        if not is_trading_day:
            state = MarketSessionState.CLOSED
        else:
            state = self._resolve_state(
                local_time.time().replace(tzinfo=None)
            )

        return MarketSessionSnapshot(
            observed_at=local_time,
            trading_date=trading_date,
            is_trading_day=is_trading_day,
            state=state,
        )

    @staticmethod
    def _resolve_state(
        current_time: time,
    ) -> MarketSessionState:
        """時刻から東京市場のセッションを判定する。"""

        if current_time < time(9, 0):
            return MarketSessionState.PRE_OPEN

        if current_time < time(11, 30):
            return MarketSessionState.MORNING

        if current_time < time(12, 30):
            return MarketSessionState.LUNCH_BREAK

        if current_time < time(15, 30):
            return MarketSessionState.AFTERNOON

        return MarketSessionState.POST_CLOSE

    @staticmethod
    def _is_weekday(
        target_date: date,
    ) -> bool:
        """土日以外を取引日候補として扱う。"""

        return target_date.weekday() < 5


class RealtimeMarketMonitor:
    """新しく確定した時間足だけを検出して保存する。"""

    def __init__(
        self,
        *,
        repository: RealtimeBarRepository,
        bar_provider: RealtimeBarProvider,
        session_service: TokyoMarketSessionService | None = None,
        interval_minutes: int = 5,
        data_source: str = "realtime",
    ) -> None:
        """Repository、Provider、監視設定を受け取る。"""

        if interval_minutes <= 0:
            raise ValueError(
                "時間足の間隔は0より大きい必要があります。"
            )

        normalized_source = data_source.strip()

        if not normalized_source:
            raise ValueError(
                "データソースを指定してください。"
            )

        self.repository = repository
        self.bar_provider = bar_provider
        self.session_service = (
            session_service
            if session_service is not None
            else TokyoMarketSessionService()
        )
        self.interval_minutes = interval_minutes
        self.data_source = normalized_source

    def poll(
        self,
        *,
        codes: Iterable[str],
        observed_at: datetime,
    ) -> RealtimeMarketPollResult:
        """市場監視を1サイクル実行する。"""

        normalized_codes = self._normalize_codes(codes)
        session = self.session_service.create_snapshot(
            observed_at
        )

        if not session.is_trading_day:
            return self._idle_result(
                session=session,
                decision=(
                    RealtimePollDecision.IDLE_NON_TRADING_DAY
                ),
                code_count=len(normalized_codes),
            )

        if not session.is_trading:
            return self._idle_result(
                session=session,
                decision=(
                    RealtimePollDecision.IDLE_OUTSIDE_MARKET_HOURS
                ),
                code_count=len(normalized_codes),
            )

        fetched: list[StockPrice] = []
        new_bars: list[StockPrice] = []

        for code in normalized_codes:
            provider_bars = self.bar_provider(
                code,
                session.trading_date,
            )
            fetched.extend(provider_bars)

            latest_saved = self.repository.latest_datetime(
                code,
                self.interval_minutes,
            )
            normalized_latest = (
                None
                if latest_saved is None
                else self._normalize_datetime(latest_saved)
            )

            candidates = self._new_completed_bars(
                provider_bars,
                code=code,
                observed_at=session.observed_at,
                latest_saved=normalized_latest,
            )
            new_bars.extend(candidates)

        ordered_new_bars = tuple(
            sorted(
                new_bars,
                key=lambda item: (
                    self._normalize_datetime(item.datetime),
                    item.code,
                ),
            )
        )

        if not ordered_new_bars:
            return RealtimeMarketPollResult(
                session=session,
                decision=RealtimePollDecision.NO_NEW_BAR,
                code_count=len(normalized_codes),
                fetched_bar_count=len(fetched),
                new_bar_count=0,
                saved_bar_count=0,
                new_bars=(),
            )

        saved_count = self.repository.save_all(
            list(ordered_new_bars),
            interval_minutes=self.interval_minutes,
            data_source=self.data_source,
        )

        return RealtimeMarketPollResult(
            session=session,
            decision=RealtimePollDecision.NEW_BARS_SAVED,
            code_count=len(normalized_codes),
            fetched_bar_count=len(fetched),
            new_bar_count=len(ordered_new_bars),
            saved_bar_count=saved_count,
            new_bars=ordered_new_bars,
        )

    def _new_completed_bars(
        self,
        prices: Iterable[StockPrice],
        *,
        code: str,
        observed_at: datetime,
        latest_saved: datetime | None,
    ) -> tuple[StockPrice, ...]:
        """未保存かつ確定済みの時間足だけ返す。"""

        unique: dict[datetime, StockPrice] = {}
        normalized_observed_at = self._normalize_datetime(
            observed_at
        )
        interval = timedelta(
            minutes=self.interval_minutes
        )

        for price in prices:
            if price.code != code:
                raise ValueError(
                    "Providerが要求銘柄と異なる時間足を返しました。 "
                    f"requested={code} actual={price.code}"
                )

            opened_at = self._normalize_datetime(
                price.datetime
            )
            closed_at = opened_at + interval

            if closed_at > normalized_observed_at:
                continue

            if (
                latest_saved is not None
                and opened_at <= latest_saved
            ):
                continue

            unique[opened_at] = price

        return tuple(
            unique[key]
            for key in sorted(unique)
        )

    @staticmethod
    def _normalize_codes(
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """銘柄コードを検証し、重複を除去する。"""

        normalized: list[str] = []

        for code in codes:
            value = code.strip()

            if not value.isdigit():
                raise ValueError(
                    "銘柄コードは数字で指定してください。"
                )

            if len(value) not in {4, 5}:
                raise ValueError(
                    "銘柄コードは4桁または5桁で指定してください。"
                )

            if value not in normalized:
                normalized.append(value)

        if not normalized:
            raise ValueError(
                "銘柄コードを1件以上指定してください。"
            )

        return tuple(normalized)

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """市場日時を日本時間へ正規化する。"""

        if value.tzinfo is None:
            return value.replace(tzinfo=JST)

        return value.astimezone(JST)

    @staticmethod
    def _idle_result(
        *,
        session: MarketSessionSnapshot,
        decision: RealtimePollDecision,
        code_count: int,
    ) -> RealtimeMarketPollResult:
        """市場時間外の空結果を作成する。"""

        return RealtimeMarketPollResult(
            session=session,
            decision=decision,
            code_count=code_count,
            fetched_bar_count=0,
            new_bar_count=0,
            saved_bar_count=0,
            new_bars=(),
        )
