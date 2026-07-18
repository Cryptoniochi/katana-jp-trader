"""Dashboard Launcherのテスト。"""

from pathlib import Path

import pytest

from app.dashboard.dashboard_launcher import (
    build_parser,
    create_launcher_app,
    dashboard_url,
    main,
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


def test_create_launcher_app_builds_fastapi_app(
    tmp_path,
) -> None:
    app = create_launcher_app(
        database_path=tmp_path / "katana.db",
        snapshot_path=tmp_path / "dashboard.json",
        history_limit=30,
    )

    assert app.title == "Project KATANA Dashboard"


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
