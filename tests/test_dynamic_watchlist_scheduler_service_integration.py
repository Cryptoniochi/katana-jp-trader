"""Dynamic Watchlist SchedulerのService統合テスト。"""

from pathlib import Path

from app.runtime.katana_service_manager import (
    build_dynamic_watchlist_scheduler_command,
)


def test_command_contains_capital_and_watchlist_settings() -> None:
    command = build_dynamic_watchlist_scheduler_command(
        database_path=Path("data/katana.db"),
        watchlist_path=Path("watchlist.txt"),
        enabled=True,
    )

    assert "app.run_dynamic_watchlist_scheduler" in command
    assert "--enable" in command
    assert "--capital-limit" in command
    assert "1000000" in command
    assert "--purchase-budget" in command
    assert "950000" in command
    assert "--minimum-symbols" in command
    assert "5" in command
