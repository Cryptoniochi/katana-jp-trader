"""kabuステーションREST Clientのテスト。"""

import json

import pytest

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_models import (
    KabuStationResponseError,
    KabuStationSymbol,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def __call__(
        self,
        method,
        url,
        headers,
        body,
        timeout_seconds,
    ):
        self.calls.append(
            (
                method,
                url,
                headers,
                body,
                timeout_seconds,
            )
        )

        if url.endswith("/token"):
            return 200, b'{"Token":"test-token"}'

        return 200, b"{}"


def client(transport) -> KabuStationClient:
    return KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="secret"
        ),
        transport=transport,
    )


def test_issue_token() -> None:
    transport = FakeTransport()
    value = client(transport)

    assert value.issue_token() == "test-token"
    method, url, headers, body, _timeout = (
        transport.calls[0]
    )
    assert method == "POST"
    assert url.endswith("/token")
    assert "X-API-KEY" not in headers
    assert json.loads(body) == {
        "APIPassword": "secret"
    }


def test_register_symbols_uses_api_key() -> None:
    transport = FakeTransport()
    value = client(transport)

    registered = value.register_symbols(
        [
            KabuStationSymbol("7203"),
            KabuStationSymbol("9984"),
        ]
    )

    assert [symbol.code for symbol in registered] == [
        "7203",
        "9984",
    ]
    _method, url, headers, body, _timeout = (
        transport.calls[-1]
    )
    assert url.endswith("/register")
    assert headers["X-API-KEY"] == "test-token"
    assert json.loads(body) == {
        "Symbols": [
            {"Symbol": "7203", "Exchange": 1},
            {"Symbol": "9984", "Exchange": 1},
        ]
    }


def test_register_rejects_more_than_limit() -> None:
    transport = FakeTransport()
    value = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="secret",
            maximum_registered_symbols=1,
        ),
        transport=transport,
    )

    with pytest.raises(ValueError, match="上限"):
        value.register_symbols(
            [
                KabuStationSymbol("7203"),
                KabuStationSymbol("9984"),
            ]
        )


def test_api_error_raises_response_error() -> None:
    def transport(
        _method,
        _url,
        _headers,
        _body,
        _timeout,
    ):
        return (
            400,
            b'{"Code":4001009,"Message":"bad request"}',
        )

    with pytest.raises(
        KabuStationResponseError,
        match="4001009",
    ):
        client(transport).issue_token()


def test_authenticated_get_reissues_token_once_after_401() -> None:
    calls = []
    token_count = 0

    def transport(method, url, headers, body, timeout):
        nonlocal token_count
        calls.append((method, url, dict(headers)))

        if url.endswith("/token"):
            token_count += 1
            token = "old-token" if token_count == 1 else "new-token"
            return 200, ('{"Token":"' + token + '"}').encode("utf-8")

        if url.endswith("/board/7203@1"):
            if headers.get("X-API-KEY") == "old-token":
                return (
                    401,
                    b'{"Code":4001009,"Message":"API key mismatch"}',
                )
            return 200, b'{"Symbol":"7203"}'

        raise AssertionError(f"unexpected request: {method} {url}")

    value = client(transport)

    result = value.board(KabuStationSymbol("7203"))

    assert result["Symbol"] == "7203"
    assert token_count == 2
    board_calls = [
        call for call in calls
        if call[1].endswith("/board/7203@1")
    ]
    assert len(board_calls) == 2
    assert board_calls[0][2]["X-API-KEY"] == "old-token"
    assert board_calls[1][2]["X-API-KEY"] == "new-token"


def test_authenticated_get_retries_only_once_after_401() -> None:
    token_count = 0
    board_count = 0

    def transport(method, url, headers, body, timeout):
        nonlocal token_count, board_count

        if url.endswith("/token"):
            token_count += 1
            return (
                200,
                ('{"Token":"token-' + str(token_count) + '"}').encode(
                    "utf-8"
                ),
            )

        if url.endswith("/board/7203@1"):
            board_count += 1
            return (
                401,
                b'{"Code":4001009,"Message":"API key mismatch"}',
            )

        raise AssertionError(f"unexpected request: {method} {url}")

    value = client(transport)

    with pytest.raises(KabuStationResponseError, match="status=401"):
        value.board(KabuStationSymbol("7203"))

    assert token_count == 2
    assert board_count == 2


def test_authenticated_post_is_not_retried_after_401() -> None:
    token_count = 0
    order_count = 0

    def transport(method, url, headers, body, timeout):
        nonlocal token_count, order_count

        if url.endswith("/token"):
            token_count += 1
            return 200, b'{"Token":"token"}'

        if url.endswith("/sendorder"):
            order_count += 1
            return (
                401,
                b'{"Code":4001009,"Message":"API key mismatch"}',
            )

        raise AssertionError(f"unexpected request: {method} {url}")

    value = client(transport)

    with pytest.raises(KabuStationResponseError, match="status=401"):
        value.send_order({"Symbol": "7203"})

    assert token_count == 1
    assert order_count == 1


class _NoopLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _enable_test_shared_token(
    value: KabuStationClient,
    path,
) -> None:
    value._shared_token_path = path
    value._shared_token_lock_path = path.with_suffix(".lock")
    value._shared_token_lock = lambda: _NoopLock()


def test_shared_token_is_reused_without_new_issue(tmp_path) -> None:
    token_path = tmp_path / "token.json"
    token_calls = 0

    def transport(method, url, headers, body, timeout):
        nonlocal token_calls

        if url.endswith("/token"):
            token_calls += 1
            return 200, b'{"Token":"shared-token"}'

        return 200, b'{"Symbol":"7203"}'

    first = client(transport)
    second = client(transport)

    _enable_test_shared_token(first, token_path)
    _enable_test_shared_token(second, token_path)

    assert first.issue_token() == "shared-token"
    assert token_calls == 1
    assert token_path.exists()

    assert second.issue_token() == "shared-token"
    assert token_calls == 1
    assert second.token == "shared-token"


def test_get_401_adopts_newer_shared_token_without_issue(
    tmp_path,
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"token":"new-token"}',
        encoding="utf-8",
    )
    token_calls = 0
    board_calls = []

    def transport(method, url, headers, body, timeout):
        nonlocal token_calls

        if url.endswith("/token"):
            token_calls += 1
            return 200, b'{"Token":"unexpected-token"}'

        if url.endswith("/board/7203@1"):
            board_calls.append(headers["X-API-KEY"])

            if headers["X-API-KEY"] == "old-token":
                return (
                    401,
                    b'{"Code":4001009,"Message":"API key mismatch"}',
                )

            return 200, b'{"Symbol":"7203"}'

        raise AssertionError(f"unexpected request: {method} {url}")

    value = client(transport)
    _enable_test_shared_token(value, token_path)
    value._token = "old-token"

    result = value.board(KabuStationSymbol("7203"))

    assert result["Symbol"] == "7203"
    assert board_calls == ["old-token", "new-token"]
    assert token_calls == 0
    assert value.token == "new-token"


def test_get_401_rotates_shared_token_when_cache_is_stale(
    tmp_path,
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"token":"old-token"}',
        encoding="utf-8",
    )
    token_calls = 0
    board_calls = []

    def transport(method, url, headers, body, timeout):
        nonlocal token_calls

        if url.endswith("/token"):
            token_calls += 1
            return 200, b'{"Token":"new-token"}'

        if url.endswith("/board/7203@1"):
            board_calls.append(headers["X-API-KEY"])

            if headers["X-API-KEY"] == "old-token":
                return (
                    401,
                    b'{"Code":4001009,"Message":"API key mismatch"}',
                )

            return 200, b'{"Symbol":"7203"}'

        raise AssertionError(f"unexpected request: {method} {url}")

    value = client(transport)
    _enable_test_shared_token(value, token_path)
    value._token = "old-token"

    result = value.board(KabuStationSymbol("7203"))

    assert result["Symbol"] == "7203"
    assert board_calls == ["old-token", "new-token"]
    assert token_calls == 1
    assert value.token == "new-token"

    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["token"] == "new-token"


def test_send_order_401_still_is_not_retried_with_shared_token(
    tmp_path,
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"token":"shared-token"}',
        encoding="utf-8",
    )
    token_calls = 0
    order_calls = 0

    def transport(method, url, headers, body, timeout):
        nonlocal token_calls, order_calls

        if url.endswith("/token"):
            token_calls += 1
            return 200, b'{"Token":"new-token"}'

        if url.endswith("/sendorder"):
            order_calls += 1
            return (
                401,
                b'{"Code":4001009,"Message":"API key mismatch"}',
            )

        raise AssertionError(f"unexpected request: {method} {url}")

    value = client(transport)
    _enable_test_shared_token(value, token_path)

    with pytest.raises(KabuStationResponseError, match="status=401"):
        value.send_order({"Symbol": "7203"})

    assert order_calls == 1
    assert token_calls == 0
