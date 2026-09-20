"""kabuステーションTCP Readiness Probeのテスト。"""

import socket
from pathlib import Path

import app.runtime.kabu_station_readiness_probe as module
from app.runtime.kabu_station_readiness_probe import probe_kabu_station_readiness


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_probe_returns_connected_when_port_is_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module.socket, "create_connection", lambda *_args, **_kwargs: FakeConnection())
    result = probe_kabu_station_readiness(environ={}, env_file=tmp_path / "missing.env")
    assert result.state == "connected"
    assert result.exit_code == 0


def test_probe_returns_disconnected_when_port_is_closed(tmp_path: Path, monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(module.socket, "create_connection", fail)
    result = probe_kabu_station_readiness(environ={}, env_file=tmp_path / "missing.env")
    assert result.state == "disconnected"
    assert "connection refused" in result.message
    assert result.exit_code == 1


def test_probe_returns_timeout_when_connection_times_out(tmp_path: Path, monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise socket.timeout()

    monkeypatch.setattr(module.socket, "create_connection", fail)
    result = probe_kabu_station_readiness(environ={}, env_file=tmp_path / "missing.env")
    assert result.state == "timeout"
    assert result.exit_code is None


def test_probe_uses_configured_base_url(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def connect(address, **kwargs):
        calls.append((address, kwargs))
        return FakeConnection()

    monkeypatch.setattr(module.socket, "create_connection", connect)
    result = probe_kabu_station_readiness(
        environ={"KABU_STATION_BASE_URL": "http://127.0.0.1:18081/kabusapi"},
        env_file=tmp_path / "missing.env",
    )
    assert result.state == "connected"
    assert calls[0][0] == ("127.0.0.1", 18081)
