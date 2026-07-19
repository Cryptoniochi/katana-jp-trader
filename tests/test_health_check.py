"""Health Check CLIのテスト。"""

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from app.database import initialize_database
from app.health_check import run
from app.runtime.paper_trading_runtime_models import (
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeBundle:
    day_service = object()
    trading_loop_component = object()
    runtime_bundle = object()
    market_monitor = object()
    paper_broker = object()
    portfolio_service = object()


class FakeCompositionFactory:
    @staticmethod
    def create(
        *,
        settings,
        now_provider=None,
        stop_requested=None,
    ):
        settings.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        initialize_database(
            settings.database_path
        )
        return FakeBundle()


def create_watchlist(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "watchlist.txt"
    path.write_text(
        "7203\n6758\n",
        encoding="utf-8",
    )
    return path


def test_health_check_returns_ready(
    tmp_path: Path,
) -> None:
    output = StringIO()
    error_output = StringIO()
    watchlist = create_watchlist(
        tmp_path
    )

    exit_code = run(
        [
            "--database-path",
            str(tmp_path / "katana.db"),
            "--watchlist",
            str(watchlist),
            "--jquants-api-key",
            "test-key",
        ],
        environ={
            "KATANA_DISCORD_WEBHOOK_URL": (
                "https://discord.test/webhook"
            ),
        },
        output=output,
        error_output=error_output,
        composition_factory=FakeCompositionFactory,
    )

    assert exit_code == 0
    assert "Project KATANA Health Check" in output.getvalue()
    assert "Overall" in output.getvalue()
    assert "READY" in output.getvalue()
    assert "Notification Channels" in output.getvalue()
    assert error_output.getvalue() == ""


def test_health_check_reports_missing_notification(
    tmp_path: Path,
) -> None:
    output = StringIO()
    watchlist = create_watchlist(
        tmp_path
    )
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text(
        "",
        encoding="utf-8",
    )

    exit_code = run(
        [
            "--env-file",
            str(empty_env_file),
            "--database-path",
            str(tmp_path / "katana.db"),
            "--watchlist",
            str(watchlist),
            "--jquants-api-key",
            "test-key",
        ],
        environ={},
        output=output,
        error_output=StringIO(),
        composition_factory=FakeCompositionFactory,
    )

    assert exit_code == 1
    assert "NOT READY" in output.getvalue()
    assert "[FAILED] Notification Channels" in output.getvalue()


def test_health_check_returns_one_on_configuration_error(
    tmp_path: Path,
) -> None:
    error_output = StringIO()

    exit_code = run(
        [
            "--watchlist",
            str(tmp_path / "missing.txt"),
        ],
        environ={},
        output=StringIO(),
        error_output=error_output,
        composition_factory=FakeCompositionFactory,
    )

    assert exit_code == 1
    assert "Health Checkを実行できませんでした" in (
        error_output.getvalue()
    )
