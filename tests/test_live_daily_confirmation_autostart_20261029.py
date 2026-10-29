from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.runtime.scheduled_paper_trading import ScheduledPaperTradingController


TOKYO = ZoneInfo("Asia/Tokyo")


def test_start_process_injects_same_day_live_confirmation(monkeypatch):
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(pid=12345)

    monkeypatch.setenv(
        "KATANA_LIVE_TRADING_CONFIRMATION",
        "KATANA-LIVE-2026-10-29",
    )

    controller = ScheduledPaperTradingController(
        enabled=True,
        now_provider=lambda: datetime(
            2026, 10, 30, 8, 45, tzinfo=TOKYO
        ),
        popen_factory=fake_popen,
    )

    monkeypatch.setattr(
        controller,
        "_record_process_event",
        lambda **kwargs: None,
    )

    controller._start_process()

    environment = captured["kwargs"]["env"]

    assert environment["KATANA_LIVE_TRADING_CONFIRMATION"] == (
        "KATANA-LIVE-2026-10-30"
    )
    assert captured["kwargs"]["cwd"] == Path.cwd()
    assert captured["command"][1:3] == [
        "-m",
        "app.run_market_session",
    ]


def test_start_process_does_not_mutate_parent_environment(monkeypatch):
    captured = {}

    def fake_popen(command, **kwargs):
        captured["env"] = kwargs["env"]
        return SimpleNamespace(pid=12345)

    monkeypatch.setenv(
        "KATANA_LIVE_TRADING_CONFIRMATION",
        "KATANA-LIVE-2026-10-29",
    )

    controller = ScheduledPaperTradingController(
        enabled=True,
        now_provider=lambda: datetime(
            2026, 10, 30, 8, 45, tzinfo=TOKYO
        ),
        popen_factory=fake_popen,
    )

    monkeypatch.setattr(
        controller,
        "_record_process_event",
        lambda **kwargs: None,
    )

    controller._start_process()

    import os

    assert os.environ["KATANA_LIVE_TRADING_CONFIRMATION"] == (
        "KATANA-LIVE-2026-10-29"
    )
    assert captured["env"]["KATANA_LIVE_TRADING_CONFIRMATION"] == (
        "KATANA-LIVE-2026-10-30"
    )
