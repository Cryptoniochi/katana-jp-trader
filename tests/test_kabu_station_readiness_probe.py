"""kabuステーションReadiness Probeのテスト。"""

from types import SimpleNamespace

import app.runtime.kabu_station_readiness_probe as module


def test_probe_returns_connected(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="ready",
            stderr="",
        ),
    )

    result = module.probe_kabu_station_readiness()

    assert result.state == "connected"
    assert result.exit_code == 0


def test_probe_returns_disconnected(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="not ready",
        ),
    )

    result = module.probe_kabu_station_readiness()

    assert result.state == "disconnected"
    assert result.exit_code == 1
