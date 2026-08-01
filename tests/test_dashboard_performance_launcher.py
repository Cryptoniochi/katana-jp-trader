"""Dashboard LauncherのPerformance接続テスト。"""

from pathlib import Path

import app.dashboard.dashboard_launcher as module


class FakeRecoveryService:
    def build_summary(self):
        raise AssertionError(
            "このテストでは呼び出しません。"
        )


def test_launcher_constructs_performance_analyzer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}

    class FakeApp:
        pass

    def fake_create_dashboard_app(**arguments):
        captured.update(arguments)
        return FakeApp()

    monkeypatch.setattr(
        module,
        "create_dashboard_app",
        fake_create_dashboard_app,
    )

    app = module.create_launcher_app(
        database_path=tmp_path / "katana.db",
        snapshot_path=tmp_path / "dashboard.json",
        history_limit=30,
        recent_trade_limit=20,
        recovery_service=FakeRecoveryService(),
    )

    assert isinstance(app, FakeApp)
    assert (
        captured["performance_service"]
        .database_path
        == tmp_path / "katana.db"
    )
