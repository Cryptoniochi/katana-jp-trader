"""リアルタイム市場監視の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.market.models import StockPrice


class MarketSessionState(StrEnum):
    """東京市場における現在のセッション状態。"""

    CLOSED = "closed"
    PRE_OPEN = "pre_open"
    MORNING = "morning"
    LUNCH_BREAK = "lunch_break"
    AFTERNOON = "afternoon"
    POST_CLOSE = "post_close"

    @property
    def is_trading(self) -> bool:
        """売買時間中か返す。"""

        return self in {
            MarketSessionState.MORNING,
            MarketSessionState.AFTERNOON,
        }


class RealtimePollDecision(StrEnum):
    """1回の市場監視処理の終了理由。"""

    IDLE_NON_TRADING_DAY = "idle_non_trading_day"
    IDLE_OUTSIDE_MARKET_HOURS = "idle_outside_market_hours"
    NO_NEW_BAR = "no_new_bar"
    NEW_BARS_SAVED = "new_bars_saved"


@dataclass(frozen=True, slots=True)
class MarketSessionSnapshot:
    """指定時点の市場セッション判定結果。"""

    observed_at: datetime
    trading_date: date
    is_trading_day: bool
    state: MarketSessionState

    def __post_init__(self) -> None:
        """日時と状態の整合性を検証する。"""

        if self.observed_at.tzinfo is None:
            raise ValueError(
                "監視日時にはタイムゾーンが必要です。"
            )

        if (
            not self.is_trading_day
            and self.state is not MarketSessionState.CLOSED
        ):
            raise ValueError(
                "非取引日の市場状態はclosedである必要があります。"
            )

    @property
    def is_trading(self) -> bool:
        """現在が取引時間中か返す。"""

        return self.is_trading_day and self.state.is_trading


@dataclass(frozen=True, slots=True)
class RealtimeMarketPollResult:
    """リアルタイム市場監視1サイクルの結果。"""

    session: MarketSessionSnapshot
    decision: RealtimePollDecision
    code_count: int
    fetched_bar_count: int
    new_bar_count: int
    saved_bar_count: int
    new_bars: tuple[StockPrice, ...]

    def __post_init__(self) -> None:
        """件数と判定結果の整合性を検証する。"""

        for name, value in {
            "銘柄数": self.code_count,
            "取得足数": self.fetched_bar_count,
            "新規足数": self.new_bar_count,
            "保存足数": self.saved_bar_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if self.new_bar_count != len(self.new_bars):
            raise ValueError(
                "新規足数と新規足一覧の件数が一致しません。"
            )

        if self.saved_bar_count > self.new_bar_count:
            raise ValueError(
                "保存足数は新規足数以下である必要があります。"
            )

        if (
            self.decision is RealtimePollDecision.NEW_BARS_SAVED
            and self.saved_bar_count <= 0
        ):
            raise ValueError(
                "新規保存結果には1件以上の保存足が必要です。"
            )

        if (
            self.decision is not RealtimePollDecision.NEW_BARS_SAVED
            and self.saved_bar_count != 0
        ):
            raise ValueError(
                "待機結果には保存足を設定できません。"
            )
