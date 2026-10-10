"""kabuステーション現物Live注文payloadの安全な構築と送信。

このモジュールは送信能力を持つが、KATANAのLive runtimeから直接は呼ばない。
上位のLive transport boundaryが、日次認証・runtime ARM・journalの
SUBMISSION_PENDINGを確認した後にだけ呼び出すことを前提とする。

初回Live activationでは意図的に現物の成行・指値だけを許可する。
STOP / STOP_LIMIT、信用取引、取消は別途明示的なレビュー対象とする。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.market.kabu_station_client import KabuStationClient, JsonObject
from app.trading.order_models import OrderSide, OrderType, TradeOrder


@dataclass(frozen=True, slots=True)
class KabuStationCashOrderSettings:
    """現物注文に必要な口座・市場設定。

    cash_buy_fund_type は口座運用に依存するため暗黙値を持たせない。
    公式APIの現物買 FundType（例: "02" または "AA"）を明示する。
    """

    exchange: int
    account_type: int
    cash_buy_fund_type: str

    def __post_init__(self) -> None:
        if self.exchange not in {1, 3, 5, 6, 9, 27}:
            raise ValueError("Unsupported kabu Station cash exchange.")
        if self.account_type not in {2, 4, 12}:
            raise ValueError("Unsupported kabu Station account type.")
        fund_type = self.cash_buy_fund_type.strip().upper()
        if fund_type not in {"02", "AA"}:
            raise ValueError(
                'cash_buy_fund_type must be explicitly set to "02" or "AA".'
            )
        object.__setattr__(self, "cash_buy_fund_type", fund_type)


class KabuStationCashOrderSender:
    """TradeOrderをkabuステーション現物注文へ変換して1回だけ送信する。"""

    def __init__(
        self,
        *,
        client: KabuStationClient,
        settings: KabuStationCashOrderSettings,
    ) -> None:
        self.client = client
        self.settings = settings

    def build_payload(self, order: TradeOrder) -> JsonObject:
        if order.order_type not in {OrderType.MARKET, OrderType.LIMIT}:
            raise ValueError(
                "Initial live activation supports MARKET and LIMIT cash orders only."
            )

        side = "2" if order.side is OrderSide.BUY else "1"
        deliv_type = 2 if order.side is OrderSide.BUY else 0
        fund_type = (
            self.settings.cash_buy_fund_type
            if order.side is OrderSide.BUY
            else "  "
        )

        if order.order_type is OrderType.MARKET:
            front_order_type = 10
            price = 0
        else:
            front_order_type = 20
            if order.limit_price is None:
                raise ValueError("LIMIT order requires limit_price.")
            price = float(order.limit_price)

        return {
            "Symbol": order.code,
            "Exchange": self.settings.exchange,
            "SecurityType": 1,
            "Side": side,
            "CashMargin": 1,
            "DelivType": deliv_type,
            "FundType": fund_type,
            "AccountType": self.settings.account_type,
            "Qty": order.quantity,
            "FrontOrderType": front_order_type,
            "Price": price,
            "ExpireDay": 0,
        }

    def send_once(self, order: TradeOrder) -> str:
        """注文を1回だけ送信し、Broker OrderIdを返す。

        例外時の自動再送は行わない。通信結果が曖昧な場合のUNKNOWN化は、
        durable journalを所有する上位transport/coordinatorの責務。
        """

        response = self.client.send_order(self.build_payload(order))
        order_id = str(response.get("OrderId") or "").strip()
        if not order_id:
            raise RuntimeError("kabu Station sendorder returned no OrderId.")
        return order_id
