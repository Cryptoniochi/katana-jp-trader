from datetime import datetime, timezone

import pytest

from app.live.live_order_idempotency_repository import (
    LiveOrderIdempotencyConflictError,
    SQLiteLiveOrderIdempotencyStore,
)


NOW = datetime(2026, 10, 3, 1, 2, 3, tzinfo=timezone.utc)


def _store(tmp_path):
    return SQLiteLiveOrderIdempotencyStore(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )


def test_store_self_initializes_table(tmp_path):
    store = _store(tmp_path)

    assert store.count() == 0


def test_first_reservation_is_new(tmp_path):
    store = _store(tmp_path)

    assert store.reserve(
        "key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    ) is True
    assert store.count() == 1


def test_identical_second_reservation_is_duplicate(tmp_path):
    store = _store(tmp_path)

    arguments = dict(
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    )

    assert store.reserve("key-1", **arguments) is True
    assert store.reserve("key-1", **arguments) is False
    assert store.count() == 1


def test_reservation_survives_repository_restart(tmp_path):
    database_path = tmp_path / "katana.db"
    first = SQLiteLiveOrderIdempotencyStore(
        database_path,
        now_provider=lambda: NOW,
    )

    assert first.reserve(
        "key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    ) is True

    second = SQLiteLiveOrderIdempotencyStore(
        database_path,
        now_provider=lambda: NOW,
    )

    assert second.reserve(
        "key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    ) is False


def test_same_key_with_different_fingerprint_is_conflict(tmp_path):
    store = _store(tmp_path)

    assert store.reserve(
        "key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    ) is True

    with pytest.raises(LiveOrderIdempotencyConflictError):
        store.reserve(
            "key-1",
            order_fingerprint="fingerprint-CHANGED",
            order_id="order-1",
            signal_id="signal-1",
        )


def test_same_key_with_different_order_id_is_conflict(tmp_path):
    store = _store(tmp_path)

    assert store.reserve(
        "key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    ) is True

    with pytest.raises(LiveOrderIdempotencyConflictError):
        store.reserve(
            "key-1",
            order_fingerprint="fingerprint-1",
            order_id="order-2",
            signal_id="signal-1",
        )


def test_get_returns_persisted_reservation(tmp_path):
    store = _store(tmp_path)
    store.reserve(
        "key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    )

    reservation = store.get("key-1")

    assert reservation is not None
    assert reservation.idempotency_key == "key-1"
    assert reservation.order_fingerprint == "fingerprint-1"
    assert reservation.order_id == "order-1"
    assert reservation.signal_id == "signal-1"
    assert reservation.reserved_at == NOW


def test_get_unknown_key_returns_none(tmp_path):
    store = _store(tmp_path)

    assert store.get("missing") is None


def test_blank_key_is_rejected(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        store.reserve(
            " ",
            order_fingerprint="fingerprint-1",
            order_id="order-1",
            signal_id="signal-1",
        )
