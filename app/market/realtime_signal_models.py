"""リアルタイム売買シグナル生成の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.trading.signal_models import TradeSignal


class RealtimeSignalDecision(StrEnum):
    """1回のリアルタイムシグナル処理結果。"""

    NO_NEW_BAR = "no_new_bar"
    BAR_PROCESSED = "bar_processed"
    SIGNALS_GENERATED = "signals_generated"


@dataclass(frozen=True, slots=True)
class RealtimeSignalProcessResult:
    """リアルタイム5分足を戦略へ適用した結果。"""

    decision: RealtimeSignalDecision
    input_bar_count: int
    processed_bar_count: int
    skipped_duplicate_count: int
    signal_count: int
    signals: tuple[TradeSignal, ...]

    def __post_init__(self) -> None:
        """件数と判定結果の整合性を検証する。"""

        for name, value in {
            "入力足数": self.input_bar_count,
            "処理足数": self.processed_bar_count,
            "重複スキップ数": self.skipped_duplicate_count,
            "シグナル数": self.signal_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if self.signal_count != len(self.signals):
            raise ValueError(
                "シグナル数とシグナル一覧の件数が一致しません。"
            )

        if (
            self.processed_bar_count
            + self.skipped_duplicate_count
            != self.input_bar_count
        ):
            raise ValueError(
                "処理足数と重複スキップ数の合計が"
                "入力足数と一致しません。"
            )

        if (
            self.decision is RealtimeSignalDecision.NO_NEW_BAR
            and self.processed_bar_count != 0
        ):
            raise ValueError(
                "新規足なし結果には処理済み足を設定できません。"
            )

        if (
            self.decision is RealtimeSignalDecision.SIGNALS_GENERATED
            and self.signal_count <= 0
        ):
            raise ValueError(
                "シグナル生成結果には1件以上の"
                "シグナルが必要です。"
            )

        if (
            self.decision is RealtimeSignalDecision.BAR_PROCESSED
            and self.signal_count != 0
        ):
            raise ValueError(
                "足処理結果にはシグナルを設定できません。"
            )
