"""kabuステーション直接Readiness Probeのテスト。"""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import app.runtime.kabu_station_readiness_probe as module
from app.runtime.kabu_station_readiness_probe import (
    probe_kabu_station_readiness,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_probe_returns_connected_when_token_is_issued(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KABU_STATION_API_PASSWORD=secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"Token": "token-value"}
        ),
    )

    result = probe_kabu_station_readiness(
        environ={},
        env_file=env_file,
    )

    assert result.state == "connected"
    assert result.exit_code == 0


def test_probe_returns_disconnected_when_port_is_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KABU_STATION_API_PASSWORD=secret\n",
        encoding="utf-8",
    )

    def fail(*_args, **_kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr(module, "urlopen", fail)

    result = probe_kabu_station_readiness(
        environ={},
        env_file=env_file,
    )

    assert result.state == "disconnected"
    assert "connection refused" in result.message


def test_probe_returns_disconnected_on_authentication_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KABU_STATION_API_PASSWORD=wrong\n",
        encoding="utf-8",
    )

    def fail(request, **_kwargs):
        raise HTTPError(
            request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(module, "urlopen", fail)

    result = probe_kabu_station_readiness(
        environ={},
        env_file=env_file,
    )

    assert result.state == "disconnected"
    assert result.exit_code == 400


def test_probe_requires_api_password(
    tmp_path: Path,
) -> None:
    result = probe_kabu_station_readiness(
        environ={},
        env_file=tmp_path / "missing.env",
    )

    assert result.state == "disconnected"
    assert "KABU_STATION_API_PASSWORD" in result.message
