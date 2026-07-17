"""リアルタイム運用ログの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class LiveLogLevel(StrEnum):
    """運用ログの重大度。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LiveLogEventType(StrEnum):
    """運用ログのイベント種別。"""

    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    CYCLE_STARTED = "cycle_started"
    CYCLE_COMPLETED = "cycle_completed"
    MARKET_POLL = "market_poll"
    SIGNAL = "signal"
    RISK = "risk"
    ORDER = "order"
    EXECUTION = "execution"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LiveOperationLogEntry:
    """JSON Linesへ保存する1件の運用ログ。"""

    occurred_at: datetime
    level: LiveLogLevel
    event_type: LiveLogEventType
    message: str
    cycle_number: int | None = None
    code: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """ログ内容を検証して正規化する。"""

        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "発生日時にはタイムゾーンが必要です。"
            )

        normalized_message = self.message.strip()

        if not normalized_message:
            raise ValueError(
                "ログメッセージを指定してください。"
            )

        if (
            self.cycle_number is not None
            and self.cycle_number <= 0
        ):
            raise ValueError(
                "サイクル番号は0より大きい必要があります。"
            )

        normalized_code = (
            None
            if self.code is None
            else self.code.strip()
        )

        if normalized_code is not None:
            if (
                not normalized_code.isdigit()
                or len(normalized_code) not in {4, 5}
            ):
                raise ValueError(
                    "銘柄コードは4桁または5桁の数字で"
                    "指定してください。"
                )

        if not isinstance(self.metadata, dict):
            raise TypeError(
                "メタデータは辞書形式で指定してください。"
            )

        object.__setattr__(
            self,
            "message",
            normalized_message,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )
        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class LiveDailyOperationSummary:
    """1営業日の運用サマリー。"""

    trading_date: date
    log_count: int
    cycle_started_count: int
    cycle_completed_count: int
    market_poll_count: int
    signal_count: int
    risk_rejected_count: int
    risk_halted_count: int
    order_count: int
    execution_count: int
    error_count: int
    critical_count: int
    codes: tuple[str, ...]

    def __post_init__(self) -> None:
        """件数と銘柄一覧を検証する。"""

        for name, value in {
            "ログ件数": self.log_count,
            "開始サイクル数": self.cycle_started_count,
            "完了サイクル数": self.cycle_completed_count,
            "市場監視数": self.market_poll_count,
            "シグナル数": self.signal_count,
            "リスク拒否数": self.risk_rejected_count,
            "リスク停止数": self.risk_halted_count,
            "注文件数": self.order_count,
            "約定件数": self.execution_count,
            "エラー件数": self.error_count,
            "重大エラー件数": self.critical_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        normalized_codes = tuple(
            sorted(
                {
                    code.strip()
                    for code in self.codes
                }
            )
        )

        if any(
            not code.isdigit()
            or len(code) not in {4, 5}
            for code in normalized_codes
        ):
            raise ValueError(
                "銘柄コードは4桁または5桁の数字で"
                "指定してください。"
            )

        object.__setattr__(
            self,
            "codes",
            normalized_codes,
        )
