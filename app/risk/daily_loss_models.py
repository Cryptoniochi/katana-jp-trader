"""日次損失制限に関するドメインモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from math import isfinite
from typing import Any


class DailyLossStatus(StrEnum):
    """日次損失制限の判定状態。"""

    ACTIVE = "active"
    WARNING = "warning"
    BLOCKED = "blocked"

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可する状態か返す。"""

        return self is not DailyLossStatus.BLOCKED

    @property
    def is_blocked(self) -> bool:
        """新規エントリー停止状態か返す。"""

        return self is DailyLossStatus.BLOCKED


class DailyLossReason(StrEnum):
    """日次損失制限の判定理由。"""

    WITHIN_LIMIT = "within_limit"
    WARNING_THRESHOLD_REACHED = "warning_threshold_reached"
    LOSS_LIMIT_REACHED = "loss_limit_reached"
    MANUALLY_BLOCKED = "manually_blocked"


@dataclass(frozen=True, slots=True)
class DailyLossPolicy:
    """日次損失制限に使用する設定。"""

    max_daily_loss: float
    warning_ratio: float = 0.8

    def __post_init__(self) -> None:
        """Policy値を検証する。"""

        if not isfinite(self.max_daily_loss):
            raise ValueError(
                "max_daily_lossは有限の数値である必要があります。"
            )

        if self.max_daily_loss <= 0:
            raise ValueError(
                "max_daily_lossは0より大きい必要があります。"
            )

        if not isfinite(self.warning_ratio):
            raise ValueError(
                "warning_ratioは有限の数値である必要があります。"
            )

        if not 0 < self.warning_ratio < 1:
            raise ValueError(
                "warning_ratioは0より大きく1未満である必要があります。"
            )

    @property
    def warning_loss(self) -> float:
        """警告開始となる損失額を返す。"""

        return self.max_daily_loss * self.warning_ratio


@dataclass(frozen=True, slots=True)
class DailyLossSnapshot:
    """ある取引日の損益状態。"""

    trading_date: date
    realized_pnl: float
    unrealized_pnl: float = 0.0
    manual_blocked: bool = False
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """Snapshot値を検証してUTCへ正規化する。"""

        for name, value in (
            ("realized_pnl", self.realized_pnl),
            ("unrealized_pnl", self.unrealized_pnl),
        ):
            if not isfinite(value):
                raise ValueError(
                    f"{name}は有限の数値である必要があります。"
                )

        normalized = self._normalize_datetime(
            self.evaluated_at
        )
        object.__setattr__(
            self,
            "evaluated_at",
            normalized,
        )

    @property
    def total_pnl(self) -> float:
        """実現損益と含み損益の合計を返す。"""

        return self.realized_pnl + self.unrealized_pnl

    @property
    def total_loss(self) -> float:
        """損失額を正の数で返す。"""

        return max(0.0, -self.total_pnl)

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """datetimeをUTCへ正規化する。"""

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class DailyLossEvaluation:
    """日次損失制限の判定結果。"""

    trading_date: date
    status: DailyLossStatus
    reason: DailyLossReason
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_loss: float
    max_daily_loss: float
    warning_loss: float
    remaining_loss_capacity: float
    evaluated_at: datetime
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """判定結果の整合性を検証する。"""

        for name, value in (
            ("realized_pnl", self.realized_pnl),
            ("unrealized_pnl", self.unrealized_pnl),
            ("total_pnl", self.total_pnl),
            ("total_loss", self.total_loss),
            ("max_daily_loss", self.max_daily_loss),
            ("warning_loss", self.warning_loss),
            (
                "remaining_loss_capacity",
                self.remaining_loss_capacity,
            ),
        ):
            if not isfinite(value):
                raise ValueError(
                    f"{name}は有限の数値である必要があります。"
                )

        if self.max_daily_loss <= 0:
            raise ValueError(
                "max_daily_lossは0より大きい必要があります。"
            )

        if not 0 < self.warning_loss < self.max_daily_loss:
            raise ValueError(
                "warning_lossは0より大きくmax_daily_loss未満である必要があります。"
            )

        expected_total_pnl = (
            self.realized_pnl + self.unrealized_pnl
        )

        if abs(self.total_pnl - expected_total_pnl) > 1e-9:
            raise ValueError(
                "total_pnlがrealized_pnlとunrealized_pnlの合計に一致しません。"
            )

        expected_total_loss = max(
            0.0,
            -self.total_pnl,
        )

        if abs(self.total_loss - expected_total_loss) > 1e-9:
            raise ValueError(
                "total_lossがtotal_pnlから計算される損失額と一致しません。"
            )

        expected_remaining = max(
            0.0,
            self.max_daily_loss - self.total_loss,
        )

        if (
            abs(
                self.remaining_loss_capacity
                - expected_remaining
            )
            > 1e-9
        ):
            raise ValueError(
                "remaining_loss_capacityが期待値と一致しません。"
            )

        normalized = DailyLossSnapshot._normalize_datetime(
            self.evaluated_at
        )
        object.__setattr__(
            self,
            "evaluated_at",
            normalized,
        )

        if self.status is DailyLossStatus.ACTIVE:
            if self.reason is not DailyLossReason.WITHIN_LIMIT:
                raise ValueError(
                    "ACTIVEのreasonはWITHIN_LIMITである必要があります。"
                )

        if self.status is DailyLossStatus.WARNING:
            if (
                self.reason
                is not DailyLossReason.WARNING_THRESHOLD_REACHED
            ):
                raise ValueError(
                    "WARNINGのreasonが不正です。"
                )

        if self.status is DailyLossStatus.BLOCKED:
            if self.reason not in {
                DailyLossReason.LOSS_LIMIT_REACHED,
                DailyLossReason.MANUALLY_BLOCKED,
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
