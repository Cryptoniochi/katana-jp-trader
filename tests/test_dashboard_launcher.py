"""Dashboard Launcherのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dashboard.dashboard_launcher import (
    build_parser,
    create_launcher_app,
    create_recovery_history_service,
    dashboard_url,
    main,
)
from app.runtime.recovery_history_models import (
    RecoveryComponent,
)
from app.runtime.recovery_history_repository import (
    RecoveryHistoryRepository,
)
from app.runtime.recovery_history_service import (
    RecoveryHistoryService,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    10,
    0,
    tzinfo=timezone.utc,
)


def create_success_result() -> RecoveryResult:
    """テスト用の成功RecoveryResultを作成する。"""

    attempt = RecoveryAttempt(
        attempt_number=1,
        started_at=NOW,
        completed_at=NOW,
        successful=True,
        error_message=None,
        delay_seconds_before_attempt=0.0,
    )

    return RecoveryResult(
        recovery_name="broker_reconnect",
        status=RecoveryStatus.SUCCESS,
        started_at=NOW,
        completed_at=NOW,
        attempts=(attempt,),
    )


def test_parser_accepts_launcher_options() -> None:
    args = build_parser().parse_args(
        [
            "--host",
            "0.0.0.0",
            "--port",
            "8080",
            "--database",
            "data/katana.db",
            "--snapshot",
            "reports/dashboard.json",
            "--history-limit",
            "60",
            "--no-browser",
            "--log-level",
            "warning",
        ]
    )

    assert args.host == "0.0.0.0"
    assert args.port == 8080
    assert args.database == Path("data/katana.db")
    assert args.snapshot == Path(
        "reports/dashboard.json"
    )
    assert args.history_limit == 60
    assert args.no_browser
    assert args.log_level == "warning"


def test_dashboard_url_normalizes_wildcard_host() -> None:
    assert dashboard_url(
        host="0.0.0.0",
        port=8000,
    ) == "http://127.0.0.1:8000"

    assert dashboard_url(
        host="localhost",
        port=9000,
    ) == "http://localhost:9000"


def test_create_recovery_history_service() -> None:
    """LauncherがRecoveryHistoryServiceを生成する。"""

    service = create_recovery_history_service()

    assert isinstance(
        service,
        RecoveryHistoryService,
    )

    summary = service.build_summary(
        generated_at=NOW,
    )

    assert summary.total_attempts == 0
    assert summary.is_healthy() is True


def test_create_launcher_app_builds_fastapi_app(
    tmp_path,
) -> None:
    app = create_launcher_app(
        database_path=tmp_path / "katana.db",
        snapshot_path=tmp_path / "dashboard.json",
        history_limit=30,
    )

    assert app.title == "Project KATANA Dashboard"


def test_launcher_app_exposes_recovery_api(
    tmp_path,
) -> None:
    """Launcher生成AppがRecovery APIを公開する。"""

    app = create_launcher_app(
        database_path=tmp_path / "katana.db",
        snapshot_path=tmp_path / "dashboard.json",
        history_limit=30,
    )
    client = TestClient(app)

    response = client.get(
        "/api/dashboard/recovery"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["aggregate"] == {
        "total_attempts": 0,
        "total_successes": 0,
        "total_failures": 0,
        "success_rate": 100.0,
    }
    assert payload["recovery_status"] == "normal"


def test_launcher_app_uses_injected_recovery_service(
    tmp_path,
) -> None:
    """注入したRecovery履歴がAPIへ反映される。"""

    repository = RecoveryHistoryRepository()
    recovery_service = RecoveryHistoryService(
        repository=repository,
    )
    recovery_service.record(
        component=RecoveryComponent.BROKER,
        result=create_success_result(),
    )

    app = create_launcher_app(
        database_path=tmp_path / "katana.db",
        snapshot_path=tmp_path / "dashboard.json",
        history_limit=30,
        recovery_service=recovery_service,
    )
    client = TestClient(app)

    response = client.get(
        "/api/dashboard/recovery"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["broker"] == {
        "attempts": 1,
        "successes": 1,
        "failures": 0,
        "last_recovery": NOW.isoformat(),
    }
    assert payload["aggregate"] == {
        "total_attempts": 1,
        "total_successes": 1,
        "total_failures": 0,
        "success_rate": 100.0,
    }


def test_main_runs_uvicorn_without_opening_browser(
    monkeypatch,
    tmp_path,
) -> None:
    calls = []

    monkeypatch.setattr(
        "app.dashboard.dashboard_launcher.uvicorn.run",
        lambda app, **kwargs: calls.append(
            (app, kwargs)
        ),
    )

    exit_code = main(
        [
            "--database",
            str(tmp_path / "katana.db"),
            "--snapshot",
            str(tmp_path / "dashboard.json"),
            "--port",
            "8123",
            "--no-browser",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0][1]["port"] == 8123
    assert calls[0][1]["host"] == "127.0.0.1"


def test_main_rejects_invalid_port() -> None:
    with pytest.raises(ValueError, match="Port"):
        main(
            [
                "--port",
                "0",
                "--no-browser",
            ]
        )