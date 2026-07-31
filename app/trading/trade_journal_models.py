"""Trade Journalの共通データモデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TradeJournalEntry:
    """BUY約定からEXIT/SELL約定までの完了トレード。"""

    trade_id: str
    strategy_name: str
    code: str
    entry_signal_id: str
    exit_signal_id: str
    entry_execution_id: str
    exit_execution_id: str
    entry_at: datetime
    exit_at: datetime
    entry_price: float
    exit_price: float
    quantity: int
    entry_cost: float
    exit_cost: float
    realized_profit_loss: float
    return_rate: float
    holding_minutes: float
    exit_reason: str | None = None
    maximum_favorable_excursion: float | None = None
    maximum_adverse_excursion: float | None = None
    maximum_favorable_excursion_rate: float | None = None
    maximum_adverse_excursion_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = {
            "trade_id": self.trade_id.strip(),
            "strategy_name": self.strategy_name.strip(),
            "code": self.code.strip(),
            "entry_signal_id": self.entry_signal_id.strip(),
            "exit_signal_id": self.exit_signal_id.strip(),
            "entry_execution_id": self.entry_execution_id.strip(),
            "exit_execution_id": self.exit_execution_id.strip(),
        }

        for name, value in normalized.items():
            if not value:
                raise ValueError(
                    f"{name}を指定してください。"
                )

        if not normalized["code"].isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized["code"]) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if self.entry_at.tzinfo is None:
            raise ValueError(
                "エントリー日時にはタイムゾーンが必要です。"
            )

        if self.exit_at.tzinfo is None:
            raise ValueError(
                "決済日時にはタイムゾーンが必要です。"
            )

        if self.exit_at < self.entry_at:
            raise ValueError(
                "決済日時はエントリー日時以後である必要があります。"
            )

        if self.entry_price <= 0 or self.exit_price <= 0:
            raise ValueError(
                "約定価格は0より大きい必要があります。"
            )

        if self.quantity <= 0:
            raise ValueError(
                "数量は0より大きい必要があります。"
            )

        if self.entry_cost < 0 or self.exit_cost < 0:
            raise ValueError(
                "取引コストは0以上である必要があります。"
            )

        if self.holding_minutes < 0:
            raise ValueError(
                "保有時間は0以上である必要があります。"
            )

        if not isinstance(self.metadata, dict):
            raise TypeError(
                "メタデータは辞書形式で指定してください。"
            )

        for name, value in normalized.items():
            object.__setattr__(self, name, value)

        object.__setattr__(
            self,
            "exit_reason",
            (
                self.exit_reason.strip()
                if self.exit_reason is not None
                and self.exit_reason.strip()
                else None
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )

    @property
    def total_cost(self) -> float:
        return self.entry_cost + self.exit_cost

    @property
    def is_win(self) -> bool:
        return self.realized_profit_loss > 0

    @property
    def is_loss(self) -> bool:
        return self.realized_profit_loss < 0


@dataclass(frozen=True, slots=True)
class TradeJournalRecord:
    """SQLiteへ保存されたTrade Journal。"""

    id: int
    entry: TradeJournalEntry
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError(
                "保存IDは0より大きい必要があります。"
            )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "作成日時にはタイムゾーンが必要です。"
            )

        if self.updated_at.tzinfo is None:
            raise ValueError(
                "更新日時にはタイムゾーンが必要です。"
            )

        if self.updated_at < self.created_at:
            raise ValueError(
                "更新日時は作成日時以後である必要があります。"
            )
