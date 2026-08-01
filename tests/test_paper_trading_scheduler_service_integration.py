"""Paper Trading SchedulerのService統合テスト。"""

from pathlib import Path

from app.runtime.katana_service_manager import (
    build_scheduled_paper_trading_command,
)


def test_scheduler_command_forwards_runtime_configuration() -> None:
    command = build_scheduled_paper_trading_command(
        database_path=Path("data/katana.db"),
        watchlist_path=Path("watchlist.txt"),
        strategies=(
            "orb",
            "pullback",
            "high-breakout",
        ),
        enabled=True,
    )

    assert "app.run_scheduled_paper_trading" in command
    assert "--enable" in command
    assert "--database-path" in command
    assert Path(
        command[
            command.index("--database-path") + 1
        ]
    ) == Path("data/katana.db")
    assert "--watchlist" in command
    assert Path(
        command[
            command.index("--watchlist") + 1
        ]
    ) == Path("watchlist.txt")
    assert command.count("--strategy") == 3
    assert "kabu-station-realtime" in command


def test_scheduler_command_can_stay_safe_disabled() -> None:
    command = build_scheduled_paper_trading_command(
        database_path=Path("data/katana.db"),
        watchlist_path=Path("watchlist.txt"),
        strategies=("orb",),
        enabled=False,
    )

    assert "--enable" not in command
