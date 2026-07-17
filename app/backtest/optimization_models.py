"""ORBパラメータ最適化の共通モデル。"""

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class OrbOptimizationParameters:
    """1回のORB最適化試行に使うパラメータ。"""

    stop_loss_rate: float | None
    take_profit_rate: float | None
    opening_range_end: time

    def __post_init__(self) -> None:
        """パラメータの妥当性を検証する。"""

        for name, value in {
            "損切り率": self.stop_loss_rate,
            "利確率": self.take_profit_rate,
        }.items():
            if value is not None and value <= 0:
                raise ValueError(
                    f"{name}は0より大きい必要があります。"
                )

    @property
    def parameter_id(self) -> str:
        """再現可能なパラメータIDを返す。"""

        stop_loss = (
            "none"
            if self.stop_loss_rate is None
            else self._format_rate(self.stop_loss_rate)
        )
        take_profit = (
            "none"
            if self.take_profit_rate is None
            else self._format_rate(self.take_profit_rate)
        )
        opening_range = self.opening_range_end.strftime(
            "%H%M"
        )

        return (
            f"sl-{stop_loss}_"
            f"tp-{take_profit}_"
            f"or-{opening_range}"
        )

    @staticmethod
    def _format_rate(value: float) -> str:
        """率をID向けの安定した文字列へ変換する。"""

        return (
            f"{value:.8f}"
            .rstrip("0")
            .rstrip(".")
            .replace(".", "p")
        )


@dataclass(frozen=True, slots=True)
class OrbOptimizationGrid:
    """ORB最適化で使用する全パラメータ組み合わせ。"""

    parameters: tuple[OrbOptimizationParameters, ...]

    def __post_init__(self) -> None:
        """パラメータIDの重複を拒否する。"""

        parameter_ids = [
            parameter.parameter_id
            for parameter in self.parameters
        ]

        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(
                "最適化パラメータIDが重複しています。"
            )

    @property
    def combination_count(self) -> int:
        """組み合わせ件数を返す。"""

        return len(self.parameters)

    def get(
        self,
        parameter_id: str,
    ) -> OrbOptimizationParameters:
        """パラメータIDに一致する組み合わせを返す。"""

        normalized = parameter_id.strip()

        if not normalized:
            raise ValueError(
                "パラメータIDを指定してください。"
            )

        for parameter in self.parameters:
            if parameter.parameter_id == normalized:
                return parameter

        raise KeyError(
            "指定された最適化パラメータが存在しません。 "
            f"parameter_id={normalized}"
        )
