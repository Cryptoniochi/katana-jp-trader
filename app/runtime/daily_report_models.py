"""Project KATANA日次取引レポートの共通データモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from math import isfinite
from typing import Any


class DailyReportStatus(StrEnum):
    """日次レポートの生成状態。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class DailyReportSummary:
    """日次レポートの主要集計値。"""

    trade_count: int
    win_count: int
    loss_count: int
    flat_count: int
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    win_rate: float | None
    profit_factor: float | None
    average_win: float | None
    average_loss: float | None
    maximum_drawdown: float | None

    def __post_init__(self) -> None:
        for name in (
            "trade_count",
            "win_count",
            "loss_count",
            "flat_count",
        ):
            value = getattr(self, name)

            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        classified_count = (
            self.win_count
            + self.loss_count
            + self.flat_count
        )

        if classified_count != self.trade_count:
            raise ValueError(
                "勝敗件数の合計が取引件数と一致しません。"
            )

        for name in (
            "gross_profit",
            "gross_loss",
            "net_profit_loss",
        ):
            value = getattr(self, name)

            if not isfinite(value):
                raise ValueError(
                    f"{name}は有限値である必要があります。"
                )

        if self.gross_profit < 0:
            raise ValueError(
                "gross_profitは0以上である必要があります。"
            )

        if self.gross_loss > 0:
            raise ValueError(
                "gross_lossは0以下である必要があります。"
            )

        self._validate_optional_ratio(
            "win_rate",
            self.win_rate,
            minimum=0.0,
            maximum=1.0,
        )
        self._validate_optional_ratio(
            "profit_factor",
            self.profit_factor,
            minimum=0.0,
            maximum=None,
        )

        for name in (
            "average_win",
            "average_loss",
            "maximum_drawdown",
        ):
            value = getattr(self, name)

            if value is not None and not isfinite(value):
                raise ValueError(
                    f"{name}は有限値またはNoneである必要があります。"
                )

        if (
            self.average_win is not None
            and self.average_win < 0
        ):
            raise ValueError(
                "average_winは0以上である必要があります。"
            )

        if (
            self.average_loss is not None
            and self.average_loss > 0
        ):
            raise ValueError(
                "average_lossは0以下である必要があります。"
            )

        if (
            self.maximum_drawdown is not None
            and self.maximum_drawdown > 0
        ):
            raise ValueError(
                "maximum_drawdownは0以下である必要があります。"
            )

    @staticmethod
    def _validate_optional_ratio(
        name: str,
        value: float | None,
        *,
        minimum: float,
        maximum: float | None,
    ) -> None:
        if value is None:
            return

        if not isfinite(value):
            raise ValueError(
                f"{name}は有限値またはNoneである必要があります。"
            )

        if value < minimum:
            raise ValueError(
                f"{name}は{minimum}以上である必要があります。"
            )

        if maximum is not None and value > maximum:
            raise ValueError(
                f"{name}は{maximum}以下である必要があります。"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON互換の辞書へ変換する。"""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class DailyReportBreakdownRow:
    """戦略別・銘柄別などの集計行。"""

    key: str
    label: str
    trade_count: int
    net_profit_loss: float
    win_rate: float | None
    profit_factor: float | None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError(
                "集計キーを指定してください。"
            )

        if not self.label.strip():
            raise ValueError(
                "表示名を指定してください。"
            )

        if self.trade_count < 0:
            raise ValueError(
                "取引件数は0以上である必要があります。"
            )

        if not isfinite(self.net_profit_loss):
            raise ValueError(
                "net_profit_lossは有限値である必要があります。"
            )

        DailyReportSummary._validate_optional_ratio(
            "win_rate",
            self.win_rate,
            minimum=0.0,
            maximum=1.0,
        )
        DailyReportSummary._validate_optional_ratio(
            "profit_factor",
            self.profit_factor,
            minimum=0.0,
            maximum=None,
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON互換の辞書へ変換する。"""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class DailyTradingReport:
    """1営業日分の日次取引レポート。"""

    report_date: date
    generated_at: datetime
    status: DailyReportStatus
    summary: DailyReportSummary
    strategy_breakdown: tuple[
        DailyReportBreakdownRow,
        ...,
    ] = ()
    symbol_breakdown: tuple[
        DailyReportBreakdownRow,
        ...,
    ] = ()
    error_count: int = 0
    recovery_count: int = 0
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError(
                "生成日時にはタイムゾーンが必要です。"
            )

        if self.error_count < 0:
            raise ValueError(
                "エラー件数は0以上である必要があります。"
            )

        if self.recovery_count < 0:
            raise ValueError(
                "復旧件数は0以上である必要があります。"
            )

        if (
            self.status is DailyReportStatus.EMPTY
            and self.summary.trade_count != 0
        ):
            raise ValueError(
                "EMPTYレポートの取引件数は0である必要があります。"
            )

        if (
            self.status is DailyReportStatus.COMPLETE
            and self.notes
        ):
            raise ValueError(
                "COMPLETEレポートには補足理由を設定できません。"
            )

        for note in self.notes:
            if not note.strip():
                raise ValueError(
                    "notesに空文字列は指定できません。"
                )

    def to_dict(self) -> dict[str, Any]:
        """JSON保存・API応答用の辞書へ変換する。"""

        return {
            "report_date": self.report_date.isoformat(),
            "generated_at": (
                self.generated_at.isoformat()
            ),
            "status": self.status.value,
            "summary": self.summary.to_dict(),
            "strategy_breakdown": [
                row.to_dict()
                for row in self.strategy_breakdown
            ],
            "symbol_breakdown": [
                row.to_dict()
                for row in self.symbol_breakdown
            ],
            "error_count": self.error_count,
            "recovery_count": self.recovery_count,
            "notes": list(self.notes),
        }
