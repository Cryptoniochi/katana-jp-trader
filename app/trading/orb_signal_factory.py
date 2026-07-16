"""ORB診断結果からBUYシグナルを生成する。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.strategy.orb_diagnostics import (
    OrbDailyDiagnostic,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


JAPAN_TIMEZONE = ZoneInfo(
    "Asia/Tokyo"
)

DEFAULT_ORB_STRATEGY_NAME = "orb"


@dataclass(frozen=True, slots=True)
class OrbSignalFactorySettings:
    """ORBシグナル生成条件。"""

    strategy_name: str = DEFAULT_ORB_STRATEGY_NAME
    quantity: int = 100
    confidence: float | None = None

    def __post_init__(self) -> None:
        """不正な設定を拒否する。"""

        normalized_strategy_name = (
            self.strategy_name.strip()
        )

        if not normalized_strategy_name:
            raise ValueError(
                "戦略名を指定してください。"
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

        object.__setattr__(
            self,
            "strategy_name",
            normalized_strategy_name,
        )


class OrbSignalFactory:
    """ORBの日次診断候補をBUYシグナルへ変換する。"""

    def __init__(
        self,
        *,
        settings: OrbSignalFactorySettings | None = None,
    ) -> None:
        """シグナル生成条件を設定する。"""

        self.settings = (
            settings
            if settings is not None
            else OrbSignalFactorySettings()
        )

    def create(
        self,
        diagnostic: OrbDailyDiagnostic,
    ) -> TradeSignal | None:
        """取引候補からBUYシグナルを生成する。

        候補条件を満たさない診断結果はNoneを返す。
        """

        if not diagnostic.trade_candidate:
            return None

        if diagnostic.rejection_reason:
            raise ValueError(
                "取引候補の診断結果に"
                "除外理由が設定されています。 "
                f"code={diagnostic.code} "
                f"reason={diagnostic.rejection_reason}"
            )

        breakout_at = diagnostic.breakout_at
        breakout_price = diagnostic.breakout_price

        if breakout_at is None:
            raise ValueError(
                "取引候補にブレイク日時がありません。 "
                f"code={diagnostic.code}"
            )

        if breakout_price is None:
            raise ValueError(
                "取引候補にブレイク価格がありません。 "
                f"code={diagnostic.code}"
            )

        generated_at = self._normalize_market_datetime(
            breakout_at
        )

        metadata = self._create_metadata(
            diagnostic
        )

        signal_id = self._create_signal_id(
            code=diagnostic.code,
            generated_at=generated_at,
            metadata=metadata,
        )

        return TradeSignal(
            signal_id=signal_id,
            code=diagnostic.code,
            strategy_name=(
                self.settings.strategy_name
            ),
            action=SignalAction.BUY,
            generated_at=generated_at,
            signal_price=breakout_price,
            quantity=self.settings.quantity,
            reason="opening_range_breakout",
            confidence=self.settings.confidence,
            metadata=metadata,
        )

    def create_many(
        self,
        diagnostics: list[OrbDailyDiagnostic],
    ) -> list[TradeSignal]:
        """複数診断結果からBUYシグナル一覧を生成する。"""

        signals: list[TradeSignal] = []

        for diagnostic in diagnostics:
            signal = self.create(
                diagnostic
            )

            if signal is not None:
                signals.append(
                    signal
                )

        return sorted(
            signals,
            key=lambda signal: (
                signal.generated_at,
                signal.code,
                signal.signal_id,
            ),
        )

    def _create_signal_id(
        self,
        *,
        code: str,
        generated_at: datetime,
        metadata: dict[str, object],
    ) -> str:
        """シグナル内容から再現可能なIDを生成する。"""

        identity = {
            "code": code,
            "strategy_name": (
                self.settings.strategy_name
            ),
            "action": SignalAction.BUY.value,
            "generated_at": (
                generated_at.isoformat()
            ),
            "metadata": metadata,
        }

        identity_json = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

        digest = hashlib.sha256(
            identity_json.encode(
                "utf-8"
            )
        ).hexdigest()[:24]

        return (
            f"{self.settings.strategy_name}"
            f"-{code}-{digest}"
        )

    @staticmethod
    def _create_metadata(
        diagnostic: OrbDailyDiagnostic,
    ) -> dict[str, object]:
        """ORB診断内容をシグナルメタデータへ変換する。"""

        return {
            "trading_date": (
                diagnostic.trading_date.isoformat()
            ),
            "bar_count": diagnostic.bar_count,
            "opening_bar_count": (
                diagnostic.opening_bar_count
            ),
            "opening_range_high": (
                diagnostic.opening_range_high
            ),
            "opening_range_volume": (
                diagnostic.opening_range_volume
            ),
            "opening_range_turnover": (
                diagnostic.opening_range_turnover
            ),
            "average_opening_volume": (
                diagnostic.average_opening_volume
            ),
            "breakout_price": (
                diagnostic.breakout_price
            ),
            "breakout_volume": (
                diagnostic.breakout_volume
            ),
            "breakout_volume_ratio": (
                diagnostic.breakout_volume_ratio
            ),
            "breakout_turnover": (
                diagnostic.breakout_turnover
            ),
            "trade_candidate": (
                diagnostic.trade_candidate
            ),
        }

    @staticmethod
    def _normalize_market_datetime(
        value: datetime,
    ) -> datetime:
        """市場日時をAsia/Tokyoの日時へ正規化する。"""

        if value.tzinfo is None:
            return value.replace(
                tzinfo=JAPAN_TIMEZONE
            )

        return value.astimezone(
            JAPAN_TIMEZONE
        )