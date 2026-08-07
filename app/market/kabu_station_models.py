"""kabuステーションAPIのデータモデル。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.market.market_data_provider import MarketDataTick


TOKYO = ZoneInfo("Asia/Tokyo")


class KabuStationResponseError(RuntimeError):
    """kabuステーションAPIがエラー応答を返した。"""


class KabuStationConnectionError(RuntimeError):
    """kabuステーションAPIへ接続できなかった。"""


@dataclass(frozen=True, slots=True)
class KabuStationSymbol:
    """kabuステーションAPIへ登録する1銘柄。"""

    code: str
    exchange: int = 1

    def __post_init__(self) -> None:
        """銘柄コードと市場コードを検証する。"""

        normalized = str(self.code).strip().upper()

        # 東証の新証券コード体系では、130A / 607A のような
        # 英字入り4桁コードが存在する。
        # 既存互換のため4～5桁の半角英数字を受け入れる。
        if not re.fullmatch(r"[0-9A-Z]{4,5}", normalized):
            raise ValueError(
                "銘柄コードは4桁または5桁の"
                "半角英数字で指定してください。 "
                f"value={self.code}"
            )

        if self.exchange <= 0:
            raise ValueError(
                "市場コードは0より大きい必要があります。"
            )

        object.__setattr__(self, "code", normalized)

    def to_payload(self) -> dict[str, int | str]:
        """API登録用のJSONオブジェクトへ変換する。"""

        return {
            "Symbol": self.code,
            "Exchange": self.exchange,
        }


def parse_push_tick(
    payload: dict[str, Any],
) -> MarketDataTick | None:
    """PUSHメッセージから約定価格更新を取り出す。"""

    symbol = str(payload.get("Symbol") or "").strip()
    price = payload.get("CurrentPrice")
    observed_at = _parse_datetime(
        payload.get("CurrentPriceTime")
    )

    if not symbol or price is None or observed_at is None:
        return None

    volume = payload.get("TradingVolume")
    exchange = int(payload.get("Exchange") or 1)

    return MarketDataTick(
        code=symbol,
        observed_at=observed_at,
        price=float(price),
        cumulative_volume=(
            None
            if volume is None
            else float(volume)
        ),
        exchange=exchange,
    )


def _parse_datetime(value: object) -> datetime | None:
    """kabuステーションAPI日時文字列を解釈する。"""

    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    try:
        parsed = datetime.fromisoformat(
            normalized.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            "kabuステーションAPIの日時形式を"
            "解釈できません。 "
            f"value={normalized}"
        ) from error

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TOKYO)

    return parsed.astimezone(TOKYO)
