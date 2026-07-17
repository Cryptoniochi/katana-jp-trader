"""Walk-Forward Optimizationの集計結果モデル。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WalkForwardPerformanceAggregate:
    """複数バックテスト結果を合算した成績。"""

    result_count: int
    trade_count: int
    winning_trade_count: int
    losing_trade_count: int
    flat_trade_count: int
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    win_rate: float | None
    profit_factor: float | None
    expectancy: float | None
    average_net_profit_loss: float | None
    maximum_drawdown: float | None

    def __post_init__(self) -> None:
        """件数・率・金額の整合性を検証する。"""

        for name, value in {
            "結果件数": self.result_count,
            "取引件数": self.trade_count,
            "勝ち取引件数": self.winning_trade_count,
            "負け取引件数": self.losing_trade_count,
            "引き分け取引件数": self.flat_trade_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if (
            self.winning_trade_count
            + self.losing_trade_count
            + self.flat_trade_count
            != self.trade_count
        ):
            raise ValueError(
                "勝敗別取引件数の合計が取引件数と一致しません。"
            )

        if self.gross_profit < 0:
            raise ValueError(
                "総利益は0以上である必要があります。"
            )

        if self.gross_loss < 0:
            raise ValueError(
                "総損失は0以上である必要があります。"
            )

        if (
            self.win_rate is not None
            and not 0.0 <= self.win_rate <= 1.0
        ):
            raise ValueError(
                "勝率は0以上1以下である必要があります。"
            )

        if (
            self.profit_factor is not None
            and self.profit_factor < 0
        ):
            raise ValueError(
                "Profit Factorは0以上である必要があります。"
            )

        if (
            self.maximum_drawdown is not None
            and not 0.0 <= self.maximum_drawdown <= 1.0
        ):
            raise ValueError(
                "最大ドローダウンは0以上1以下である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class WalkForwardParameterFrequency:
    """検証期間へ採用されたパラメータの出現回数。"""

    parameter_id: str
    selected_count: int

    def __post_init__(self) -> None:
        """パラメータIDと採用回数を検証する。"""

        normalized = self.parameter_id.strip()

        if not normalized:
            raise ValueError(
                "パラメータIDを指定してください。"
            )

        if self.selected_count <= 0:
            raise ValueError(
                "採用回数は0より大きい必要があります。"
            )

        object.__setattr__(
            self,
            "parameter_id",
            normalized,
        )


@dataclass(frozen=True, slots=True)
class WalkForwardSummary:
    """Walk-Forward全体のOOS集計結果。"""

    window_count: int
    completed_window_count: int
    failed_window_count: int
    profitable_validation_window_count: int
    validation_profitable_window_rate: float | None
    training: WalkForwardPerformanceAggregate
    validation: WalkForwardPerformanceAggregate
    parameter_frequencies: tuple[
        WalkForwardParameterFrequency,
        ...
    ]

    def __post_init__(self) -> None:
        """件数と採用パラメータ一覧を検証する。"""

        for name, value in {
            "ウィンドウ件数": self.window_count,
            "完了ウィンドウ件数": self.completed_window_count,
            "失敗ウィンドウ件数": self.failed_window_count,
            "利益検証ウィンドウ件数": (
                self.profitable_validation_window_count
            ),
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if (
            self.completed_window_count
            + self.failed_window_count
            != self.window_count
        ):
            raise ValueError(
                "完了件数と失敗件数の合計が"
                "ウィンドウ件数と一致しません。"
            )

        if (
            self.profitable_validation_window_count
            > self.completed_window_count
        ):
            raise ValueError(
                "利益検証ウィンドウ件数は"
                "完了ウィンドウ件数以下である必要があります。"
            )

        if (
            self.validation_profitable_window_rate is not None
            and not 0.0
            <= self.validation_profitable_window_rate
            <= 1.0
        ):
            raise ValueError(
                "利益検証ウィンドウ率は"
                "0以上1以下である必要があります。"
            )

        parameter_ids = [
            item.parameter_id
            for item in self.parameter_frequencies
        ]

        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(
                "採用パラメータIDが重複しています。"
            )
