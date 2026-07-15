"""売買シグナルの共通データモデル。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SignalAction(StrEnum):
    """売買シグナルの指示種別。"""

    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"


class SignalStatus(StrEnum):
    """保存済み売買シグナルの処理状態。"""

    PENDING = "pending"
    PROCESSED = "processed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """処理が終了した状態か返す。"""

        return self in {
            SignalStatus.PROCESSED,
            SignalStatus.CANCELLED,
        }


@dataclass(frozen=True, slots=True)
class TradeSignal:
    """戦略から生成された1件の売買シグナル。"""

    signal_id: str
    code: str
    strategy_name: str
    action: SignalAction
    generated_at: datetime
    signal_price: float
    quantity: int
    reason: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """不正なシグナルを拒否し、文字列を正規化する。"""

        normalized_signal_id = self.signal_id.strip()
        normalized_code = self.code.strip()
        normalized_strategy_name = self.strategy_name.strip()
        normalized_reason = self.reason.strip()

        if not normalized_signal_id:
            raise ValueError(
                "シグナルIDを指定してください。"
            )

        if not normalized_code:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {
            4,
            5,
        }:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        if not normalized_strategy_name:
            raise ValueError(
                "戦略名を指定してください。"
            )

        if not normalized_reason:
            raise ValueError(
                "シグナル理由を指定してください。"
            )

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "シグナル生成日時にはタイムゾーンが必要です。"
            )

        if self.signal_price <= 0:
            raise ValueError(
                "シグナル価格は0より大きい必要があります。"
            )

        if self.quantity <= 0:
            raise ValueError(
                "数量は0より大きい必要があります。"
            )

        if self.confidence is not None and not (
            0.0 <= self.confidence <= 1.0
        ):
            raise ValueError(
                "信頼度は0以上1以下で指定してください。"
            )

        if not isinstance(
            self.metadata,
            dict,
        ):
            raise TypeError(
                "メタデータは辞書形式で指定してください。"
            )

        object.__setattr__(
            self,
            "signal_id",
            normalized_signal_id,
        )
        object.__setattr__(
            self,
            "code",
            normalized_code,
        )
        object.__setattr__(
            self,
            "strategy_name",
            normalized_strategy_name,
        )
        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )
        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class TradeSignalRecord:
    """SQLiteへ保存された売買シグナル。"""

    id: int
    signal: TradeSignal
    status: SignalStatus
    processed_at: datetime | None
    process_note: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """保存済みシグナルの整合性を検証する。"""

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

        if (
            self.processed_at is not None
            and self.processed_at.tzinfo is None
        ):
            raise ValueError(
                "処理日時にはタイムゾーンが必要です。"
            )

        if (
            self.status is SignalStatus.PENDING
            and self.processed_at is not None
        ):
            raise ValueError(
                "未処理シグナルには処理日時を設定できません。"
            )

        if (
            self.status.is_terminal
            and self.processed_at is None
        ):
            raise ValueError(
                "処理済みシグナルには処理日時が必要です。"
            )

    @property
    def signal_id(self) -> str:
        """シグナルIDを返す。"""

        return self.signal.signal_id

    @property
    def code(self) -> str:
        """銘柄コードを返す。"""

        return self.signal.code

    @property
    def strategy_name(self) -> str:
        """戦略名を返す。"""

        return self.signal.strategy_name

    @property
    def action(self) -> SignalAction:
        """売買指示を返す。"""

        return self.signal.action

    @property
    def is_pending(self) -> bool:
        """未処理状態か返す。"""

        return self.status is SignalStatus.PENDING

    @property
    def is_processed(self) -> bool:
        """処理済み状態か返す。"""

        return self.status is SignalStatus.PROCESSED

    @property
    def is_cancelled(self) -> bool:
        """取消済み状態か返す。"""

        return self.status is SignalStatus.CANCELLED