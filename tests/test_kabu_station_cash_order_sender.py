"""Tests for the kabu Station live cash-order sending primitive."""
from __future__ import annotations

import json

import pytest

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.live.kabu_station_cash_order_sender import (
    KabuStationCashOrderSender,
    KabuStationCashOrderSettings,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


def _order(
    *,
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> TradeOrder:
    return TradeOrder(
        order_id="order-1",
        signal_id="signal-1",
        code="7203",
        side=side,
        order_type=order_type,
        quantity=100,
        limit_price=limit_price,
        stop_price=stop_price,
    )


def _sender():
    calls = []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url, headers, body, timeout))
        if url.endswith("/token"):
            return 200, b'{"ResultCode":0,"Token":"token"}'
        if url.endswith("/sendorder"):
            return 200, b'{"Result":0,"OrderId":"broker-123"}'
        raise AssertionError(url)

    client = KabuStationClient(
        settings=KabuStationClientSettings(api_password="pw"),
        transport=transport,
    )
    sender = KabuStationCashOrderSender(
        client=client,
        settings=KabuStationCashOrderSettings(
            exchange=27,
            account_type=4,
            cash_buy_fund_type="02",
        ),
    )
    return sender, calls


def test_market_buy_payload_matches_cash_order_contract():
    sender, _ = _sender()
    payload = sender.build_payload(_order())

    assert payload == {
        "Symbol": "7203",
        "Exchange": 27,
        "SecurityType": 1,
        "Side": "2",
        "CashMargin": 1,
        "DelivType": 2,
        "FundType": "02",
        "AccountType": 4,
        "Qty": 100,
        "FrontOrderType": 10,
        "Price": 0,
        "ExpireDay": 0,
    }


def test_limit_sell_payload_uses_sell_specific_fields():
    sender, _ = _sender()
    payload = sender.build_payload(
        _order(
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            limit_price=2500.5,
        )
    )

    assert payload["Side"] == "1"
    assert payload["DelivType"] == 0
    assert payload["FundType"] == "  "
    assert payload["FrontOrderType"] == 20
    assert payload["Price"] == 2500.5


def test_stop_orders_remain_blocked_in_initial_live_activation():
    sender, _ = _sender()

    with pytest.raises(ValueError, match="MARKET and LIMIT"):
        sender.build_payload(
            _order(order_type=OrderType.STOP, stop_price=2400.0)
        )


def test_fund_type_must_be_explicit_and_supported():
    with pytest.raises(ValueError, match="cash_buy_fund_type"):
        KabuStationCashOrderSettings(
            exchange=27,
            account_type=4,
            cash_buy_fund_type="",
        )


def test_send_once_calls_sendorder_exactly_once_and_returns_order_id():
    sender, calls = _sender()

    result = sender.send_once(_order())

    assert result == "broker-123"
    send_calls = [item for item in calls if item[1].endswith("/sendorder")]
    assert len(send_calls) == 1
    method, _, headers, body, _ = send_calls[0]
    assert method == "POST"
    assert headers["X-API-KEY"] == "token"
    assert json.loads(body.decode("utf-8"))["Symbol"] == "7203"


def test_send_once_has_no_retry_on_transport_failure():
    attempts = 0

    def transport(method, url, headers, body, timeout):
        nonlocal attempts
        if url.endswith("/token"):
            return 200, b'{"ResultCode":0,"Token":"token"}'
        if url.endswith("/sendorder"):
            attempts += 1
            raise TimeoutError("ambiguous transport timeout")
        raise AssertionError(url)

    client = KabuStationClient(
        settings=KabuStationClientSettings(api_password="pw"),
        transport=transport,
    )
    sender = KabuStationCashOrderSender(
        client=client,
        settings=KabuStationCashOrderSettings(
            exchange=27,
            account_type=4,
            cash_buy_fund_type="02",
        ),
    )

    with pytest.raises(Exception):
        sender.send_once(_order())

    assert attempts == 1
