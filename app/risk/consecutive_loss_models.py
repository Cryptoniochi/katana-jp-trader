"""連敗停止機能に関するドメインモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from math import isfinite
from typing import Any


class ConsecutiveLossStatus(StrEnum):
    """連敗停止機能の判定状態。"""

    ACTIVE = "active"
    WARNING = "warning"
    BLOCKED = "blocked"

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可する状態か返す。"""

        return self is not ConsecutiveLossStatus.BLOCKED

    @property
    def is_blocked(self) -> bool:
        """新規エントリー停止状態か返す。"""

        return self is ConsecutiveLossStatus.BLOCKED


class ConsecutiveLossReason(StrEnum):
    """連敗停止機能の判定理由。"""

    WITHIN_LIMIT = "within_limit"
    WARNING_THRESHOLD_REACHED = "warning_threshold_reached"
    LOSS_LIMIT_REACHED = "loss_limit_reached"
    MANUALLY_BLOCKED = "manually_blocked"


@dataclass(frozen=True, slots=True)
class ConsecutiveLossPolicy:
    """連敗停止機能に使用する設定。"""

    max_consecutive_losses: int
    warning_consecutive_losses: int | None = None

    def __post_init__(self) -> None:
        """Policy値を検証して警告値を補完する。"""

        if self.max_consecutive_losses < 1:
            raise ValueError(
                "max_consecutive_lossesは1以上である必要があります。"
            )

        warning_value = self.warning_consecutive_losses

        if warning_value is None:
            warning_value = max(
                1,
                self.max_consecutive_losses - 1,
            )
            object.__setattr__(
                self,
                "warning_consecutive_losses",
                warning_value,
            )

        if warning_value < 1:
            raise ValueError(
                "warning_consecutive_lossesは1以上である必要があります。"
            )

        if warning_value >= self.max_consecutive_losses:
            raise ValueError(
                "warning_consecutive_lossesはmax_consecutive_losses未満である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class ConsecutiveLossSnapshot:
    """ある時点の連敗状態。"""

    trading_date: date
    consecutive_losses: int
    last_trade_pnl: float | None = None
    manual_blocked: bool = False
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """Snapshot値を検証してUTCへ正規化する。"""

        if self.consecutive_losses < 0:
            raise ValueError(
                "consecutive_lossesは0以上である必要があります。"
            )

        if (
            self.last_trade_pnl is not None
            and not isfinite(self.last_trade_pnl)
        ):
            raise ValueError(
                "last_trade_pnlは有限の数値である必要があります。"
            )

        normalized = self._normalize_datetime(
            self.evaluated_at
        )
        object.__setattr__(
            self,
            "evaluated_at",
            normalized,
        )

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """datetimeをUTCへ正規化する。"""

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ConsecutiveLossEvaluation:
    """連敗停止機能の判定結果。"""

    trading_date: date
    status: ConsecutiveLossStatus
    reason: ConsecutiveLossReason
    consecutive_losses: int
    warning_consecutive_losses: int
    max_consecutive_losses: int
    remaining_losses_before_block: int
    last_trade_pnl: float | None
    evaluated_at: datetime
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """判定結果の整合性を検証する。"""

        if self.consecutive_losses < 0:
            raise ValueError(
                "consecutive_lossesは0以上である必要があります。"
            )

        if self.warning_consecutive_losses < 1:
            raise ValueError(
                "warning_consecutive_lossesは1以上である必要があります。"
            )

        if self.max_consecutive_losses < 1:
            raise ValueError(
                "max_consecutive_lossesは1以上である必要があります。"
            )

        if (
            self.warning_consecutive_losses
            >= self.max_consecutive_losses
        ):
            raise ValueError(
                "warning_consecutive_lossesはmax_consecutive_losses未満である必要があります。"
            )

        expected_remaining = max(
            0,
            self.max_consecutive_losses - self.consecutive_losses,
        )

        if self.remaining_losses_before_block != expected_remaining:
            raise ValueError(
                "remaining_losses_before_blockが期待値と一致しません。"
            )

        if (
            self.last_trade_pnl is not None
            and not isfinite(self.last_trade_pnl)
        ):
            raise ValueError(
                "last_trade_pnlは有限の数値である必要があります。"
            )

        normalized = ConsecutiveLossSnapshot._normalize_datetime(
            self.evaluated_at
        )
        object.__setattr__(
            self,
            "evaluated_at",
            normalized,
        )

        if self.status is ConsecutiveLossStatus.ACTIVE:
            if self.reason is not ConsecutiveLossReason.WITHIN_LIMIT:
                raise ValueError(
                    "ACTIVEのreasonはWITHIN_LIMITである必要があります。"
                )

        if self.status is ConsecutiveLossStatus.WARNING:
            if (
                self.reason
                is not ConsecutiveLossReason.WARNING_THRESHOLD_REACHED
            ):
                raise ValueError(
                    "WARNINGのreasonが不正です。"
                )

        if self.status is ConsecutiveLossStatus.BLOCKED:
            if self.reason not in {
                ConsecutiveLossReason.LOSS_LIMIT_REACHED,
                ConsecutiveLossReason.MANUALLY_BLOCKED,
            }:
                raise ValueError(
                    "BLOCKEDのreasonが不正です。"
                )

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.status.allows_new_entries

    @property
    def is_blocked(self) -> bool:
        """新規エントリー停止状態か返す。"""

        return self.status.is_blocked
